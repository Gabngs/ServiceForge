"""Visor del estándar del proyecto (documentación empaquetada con la app).

Los `.md` viven en `standard_docs/` (`Backend/` y `Frontend/`, copia de las
notas "Template Estandar Backend/Frontend" del vault de Obsidian, con sus
[[wikilinks]]) y se leen tal cual estén en disco en cada apertura — este
módulo no cachea nada, así que "Actualizar estándar" (ver gui.py) alcanza
para reflejar un cambio sin tocar código ni recompilar el .exe.

Dos ubicaciones, mismo criterio que `settings.py`/`logs.py` para lo que debe
sobrevivir a una reinstalación:
  - `_BUNDLED_DIR`      -> va empaquetada en el .exe (ver generador.spec),
                            es la copia "de fábrica" del estándar.
  - `override_docs_dir()` -> %APPDATA%/ServiceForge/standard_docs, la escribe
                            el botón "Actualizar estándar" de la GUI. Si
                            existe y tiene contenido, gana sobre la bundled --
                            así una empresa que reusa la app puede cambiar el
                            estándar (estructura de carpetas, nomenclaturas,
                            etc.) sin tocar el instalador.
"""

from __future__ import annotations

import html as _html
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

import markdown as _markdown

_BUNDLED_DIR = Path(__file__).parent / "standard_docs"

WIKILINK_SCHEME = "wikilink:"

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")

_CODE_BLOCK_RE = re.compile(
    r'<pre><code(?:\s+class="language-(?P<lang>[\w+-]*)")?>(?P<code>.*?)</code></pre>',
    re.DOTALL,
)

_CODE_TOKEN_RE = re.compile(
    r"(?P<comment>//[^\n]*|#[^\n]*|/\*.*?\*/)"
    r"|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
    r"|(?P<variable>\$[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)",
    re.DOTALL,
)

# Un subconjunto de keywords PHP/TS -- suficiente para diferenciar visualmente
# estructura de nombres propios, no un lexer completo del lenguaje.
_PHP_KEYWORDS = frozenset(
    """abstract and array as break callable case catch class clone const continue
    declare default do echo else elseif empty enddeclare endfor endforeach endif
    endswitch endwhile extends final finally fn for foreach function global goto
    if implements include include_once instanceof insteadof interface isset list
    match namespace new or print private protected public readonly require
    require_once return static switch throw trait try unset use var while xor
    yield void int string bool float mixed null true false self parent""".split()
)

_TS_KEYWORDS = frozenset(
    """const let var function return if else for while do switch case default
    break continue class extends implements interface type enum import export
    from as new this super try catch finally throw typeof instanceof in of void
    null undefined true false async await public private protected readonly
    static abstract namespace declare get set""".split()
)

# Paleta tipo VS Code (Dark+/Light+) -- separada de theme.py porque son colores
# de sintaxis (fijos por lenguaje), no de UI.
SYNTAX_COLORS = {
    "dark": {
        "keyword": "#c586c0",
        "string": "#ce9178",
        "comment": "#6a9955",
        "variable": "#9cdcfe",
        "number": "#b5cea8",
        "function": "#dcdcaa",
        "type": "#4ec9b0",
    },
    "light": {
        "keyword": "#af00db",
        "string": "#a31515",
        "comment": "#008000",
        "variable": "#001080",
        "number": "#098658",
        "function": "#795e26",
        "type": "#267f99",
    },
}


def override_docs_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ServiceForge" / "standard_docs"


def active_docs_dir() -> Path:
    """Carpeta que se muestra en el visor: la actualizada por el usuario si
    existe y tiene contenido, si no la que viene empaquetada con la app."""
    override = override_docs_dir()
    if override.is_dir() and any(override.rglob("*.md")):
        return override
    return _BUNDLED_DIR


def is_using_override() -> bool:
    return active_docs_dir() == override_docs_dir()


@dataclass
class DocNode:
    name: str
    path: Path | None  # None para carpetas
    children: list["DocNode"] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return self.path is None


def build_tree(root: Path) -> DocNode:
    """Árbol de carpetas/notas de `root`, tal cual está en disco -- mismo
    layout que el vault de Obsidian, para que sea reconocible de un vistazo."""

    def _walk(dir_path: Path, name: str) -> DocNode:
        node = DocNode(name=name, path=None)
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return node
        for entry in entries:
            if entry.is_dir():
                child = _walk(entry, entry.name)
                if child.children:
                    node.children.append(child)
            elif entry.suffix.lower() == ".md":
                node.children.append(DocNode(name=entry.stem, path=entry))
        return node

    return _walk(root, root.name)


def index_by_title(root: Path) -> dict[str, Path]:
    """Título de nota (nombre de archivo sin extensión, en minúscula) -> Path.
    Misma resolución que usa Obsidian para [[wikilinks]]: por título, sin
    importar en qué subcarpeta viva la nota."""
    index: dict[str, Path] = {}
    for md_file in root.rglob("*.md"):
        index[md_file.stem.lower()] = md_file
    return index


def _wikilinks_to_markdown_links(text: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        target = m.group(1).strip()
        alias = (m.group(2) or target).strip()
        return f"[{alias}]({WIKILINK_SCHEME}{quote(target)})"

    return _WIKILINK_RE.sub(_sub, text)


def wikilink_target(url: str) -> str | None:
    """Si `url` es un link [[wikilink]] convertido (ver `_wikilinks_to_markdown_links`),
    devuelve el título de la nota destino; si no, None."""
    if not url.startswith(WIKILINK_SCHEME):
        return None
    return unquote(url[len(WIKILINK_SCHEME):])


def _highlight_code(code: str, lang: str, colors: dict[str, str]) -> str:
    keywords = _TS_KEYWORDS if lang in ("ts", "typescript", "js", "javascript") else _PHP_KEYWORDS
    out: list[str] = []
    pos = 0
    for m in _CODE_TOKEN_RE.finditer(code):
        out.append(_html.escape(code[pos:m.start()]))
        pos = m.end()
        token = m.group()
        escaped = _html.escape(token)
        kind = m.lastgroup
        color: str | None = None
        if kind == "comment":
            color = colors["comment"]
        elif kind == "string":
            color = colors["string"]
        elif kind == "variable":
            color = colors["variable"]
        elif kind == "number":
            color = colors["number"]
        elif kind == "word":
            if token in keywords:
                color = colors["keyword"]
            elif code[m.end():m.end() + 1].lstrip() != "" and code[m.end():].lstrip(" \t")[:1] == "(":
                color = colors["function"]
            elif token[:1].isupper():
                color = colors["type"]
        out.append(f'<span style="color:{color}">{escaped}</span>' if color else escaped)
    out.append(_html.escape(code[pos:]))
    return "".join(out)


def _highlight_html_code_blocks(html_text: str, colors: dict[str, str]) -> str:
    def _sub(m: re.Match[str]) -> str:
        raw = _html.unescape(m.group("code"))
        lang = (m.group("lang") or "").lower()
        return f"<pre><code>{_highlight_code(raw, lang, colors)}</code></pre>"

    return _CODE_BLOCK_RE.sub(_sub, html_text)


def render_note_html(md_path: Path, theme: dict[str, str], mode: str = "dark") -> str:
    """Markdown -> HTML listo para `QTextBrowser.setHtml()`: wikilinks como
    links clickeables (esquema `wikilink:`) y bloques de código con resaltado
    de sintaxis, coloreados según el tema activo (ver theme.py)."""
    raw = md_path.read_text(encoding="utf-8")
    linked = _wikilinks_to_markdown_links(raw)
    body_html = _markdown.markdown(linked, extensions=["fenced_code", "tables", "sane_lists"])
    syntax = SYNTAX_COLORS.get(mode, SYNTAX_COLORS["dark"])
    body_html = _highlight_html_code_blocks(body_html, syntax)

    return f"""<html><head><style>
body {{ color: {theme['text']}; font-family: "Segoe UI", sans-serif; font-size: 10.5pt; }}
h1, h2, h3 {{ color: {theme['text']}; border-bottom: 1px solid {theme['border']}; padding-bottom: 4px; }}
a {{ color: {theme['accent']}; text-decoration: none; }}
p code, li code, td code {{ background-color: {theme['code_bg']}; color: {theme['code_text']};
    padding: 1px 4px; border-radius: 3px; font-family: Consolas, "Courier New", monospace; }}
pre {{ background-color: {theme['code_bg']}; padding: 10px; border-radius: 6px;
    border: 1px solid {theme['border']}; }}
pre code {{ background: none; padding: 0; font-family: Consolas, "Courier New", monospace; }}
table {{ border-collapse: collapse; margin: 8px 0; }}
th, td {{ border: 1px solid {theme['border']}; padding: 4px 10px; }}
th {{ background-color: {theme['surface_alt']}; }}
blockquote {{ color: {theme['text_muted']}; border-left: 3px solid {theme['border']}; margin: 4px 0; padding-left: 10px; }}
</style></head><body>
{body_html}
</body></html>"""


def replace_docs(source_dir: Path) -> int:
    """Reemplaza la carpeta de override completa por una copia de `source_dir`
    (carpeta con los .md actualizados, misma estructura que `standard_docs/`).
    Devuelve la cantidad de notas copiadas."""
    dest = override_docs_dir()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source_dir, dest)
    return sum(1 for _ in dest.rglob("*.md"))


def restore_bundled_docs() -> None:
    """Borra el override -- el visor vuelve a mostrar el estándar empaquetado
    con la app."""
    dest = override_docs_dir()
    if dest.exists():
        shutil.rmtree(dest)
