"""Revisa un sitio bilingüe de GitHub Pages ANTES de publicarlo.

Uso (desde la raíz del repositorio del sitio):
    python scripts/verificar_sitio.py
    python scripts/verificar_sitio.py --raiz ruta/al/sitio

Qué revisa (solo biblioteca estándar de Python):
  1. Que existan la página en español (index.md) y la de inglés (en/index.md).
  2. Paridad: mismo número de secciones (encabezados de nivel 2) en ambos idiomas,
     y un enlace de cambio de idioma en cada página.
  3. Marcas de trabajo sin resolver: [COMPLETA...], [FALTA DATO...], [CONFIRMAR...],
     [CHECK...], TODO y el texto USUARIO. Se buscan en el texto de cada página, en el
     title: del bloque inicial (---) y en _config.yml (title: y description:).
  4. Datos sensibles: posibles teléfonos, correos que parecen teléfono, posibles
     domicilios y posibles llaves o tokens.
  5. Enlaces locales rotos (archivos que no existen en el repositorio).
  6. (Lab 1 v4) Que exista proyecto/ficha-proyecto.md con las secciones Proyecto elegido,
     Problema, Usuario y Criterio de éxito (con texto propio: «Sin definir» cuenta como
     pendiente), y que todo lo que hay en proyecto/ también pase las revisiones de
     privacidad, llaves y marcas.

Sale con código 1 si encuentra algo, para que también sirva en una Acción de GitHub.

LIMITACIÓN HONESTA: son reglas heurísticas. Pueden dar falsos positivos y NO detectan
todo (por ejemplo, el nombre de un cliente o un domicilio escrito de forma inusual).
La revisión de privacidad humana sigue siendo obligatoria.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PAGINAS = {"es": Path("index.md"), "en": Path("en/index.md")}

# --- Marcas de trabajo -------------------------------------------------------------
MARCAS = re.compile(
    r"\[(?:COMPLETA|FALTA DATO|CONFIRMAR|CHECK)[^\]]*\]|\bTODO\b|\bUSUARIO\b"
)

# --- Datos sensibles ---------------------------------------------------------------
# Teléfono: de 10 a 13 dígitos, con espacios, guiones, puntos o paréntesis opcionales.
TELEFONO = re.compile(r"(?<![\w\d])\+?(?:\(?\d{1,4}\)?[\s.-]?){2,5}\d{2,4}(?![\w\d])")
CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Domicilio probable: palabra típica de dirección seguida de un nombre y un número,
# o un código postal explícito.
DOMICILIO = re.compile(
    r"(?i)"
    r"\b(?:calle|av\.?|avenida|blvd\.?|boulevard|calzada|carrera|cra\.?|jir[oó]n|"
    r"pasaje|manzana|mz\.?|lote|lt\.?|street|st\.|avenue|ave\.|road|rd\.)"
    r"\s+[\w .ÁÉÍÓÚÑáéíóúñ'-]{1,40}?\s*(?:no\.?|n[úu]m\.?|#)?\s*\d{1,5}\b"
    r"|\b(?:c\.?\s?p\.?|c[oó]digo postal|zip(?: code)?|postal code)\s*:?\s*\d{4,6}\b"
    r"|\b(?:domicilio|direcci[oó]n particular|home address)\s*:"
)
LLAVES = [
    ("llave de acceso de AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token de GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("llave de Google (AIza...)", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("llave tipo sk-...", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("bloque de llave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

ENLACE_MD = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


@dataclass(frozen=True)
class Problema:
    categoria: str  # paginas | paridad | marcas | telefono | correo | domicilio | llave | enlace
    archivo: str
    mensaje: str

    def __str__(self) -> str:
        return f"[{self.categoria}] {self.archivo}: {self.mensaje}"


def leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def quitar_front_matter(texto: str) -> str:
    return re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", texto, flags=re.S)


def front_matter(texto: str) -> str:
    """Devuelve el bloque entre las dos líneas --- del inicio (sin ellas), o cadena vacía."""
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", texto, flags=re.S)
    return m.group(1) if m else ""


def sin_comentarios_yaml(texto: str) -> str:
    """Quita las líneas de comentario de YAML (las que empiezan con #)."""
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


def secciones(texto: str) -> list[str]:
    cuerpo = quitar_front_matter(texto)
    cuerpo = re.sub(r"```.*?```", "", cuerpo, flags=re.S)  # ignora bloques de código
    return re.findall(r"^##\s+(.+?)\s*$", cuerpo, flags=re.M)


def sin_urls(texto: str) -> str:
    """Quita las URL para no confundir identificadores largos con teléfonos."""
    texto = re.sub(r"\]\([^)]*\)", "]()", texto)
    return re.sub(r"https?://\S+", "", texto)


def digitos(cadena: str) -> int:
    return sum(c.isdigit() for c in cadena)


def revisar_telefonos(archivo: str, texto: str) -> list[Problema]:
    problemas = []
    limpio = sin_urls(quitar_front_matter(texto))
    limpio = CORREO.sub(" ", limpio)  # los correos se revisan aparte
    for m in TELEFONO.finditer(limpio):
        trozo = m.group(0).strip()
        n = digitos(trozo)
        if not 10 <= n <= 13:
            continue
        # Evita rangos de años como «2019-2024 2025» (todos de 4 dígitos y empiezan en 19/20)
        grupos = re.findall(r"\d+", trozo)
        if all(len(g) == 4 and g[:2] in ("19", "20") for g in grupos):
            continue
        problemas.append(Problema("telefono", archivo, f"posible teléfono: «{trozo}»"))
    return problemas


def revisar_correos(archivo: str, texto: str) -> list[Problema]:
    problemas = []
    for correo in CORREO.findall(quitar_front_matter(texto)):
        local = correo.split("@", 1)[0]
        if digitos(local) >= 7:
            problemas.append(
                Problema("correo", archivo, f"el correo «{correo}» parece contener un teléfono")
            )
    return problemas


def revisar_domicilios(archivo: str, texto: str) -> list[Problema]:
    limpio = sin_urls(quitar_front_matter(texto))
    limpio = re.sub(r"```.*?```", "", limpio, flags=re.S)
    return [
        Problema("domicilio", archivo, f"posible domicilio: «{m.group(0).strip()}»")
        for m in DOMICILIO.finditer(limpio)
    ]


def revisar_llaves(archivo: str, texto: str) -> list[Problema]:
    problemas = []
    for nombre, patron in LLAVES:
        if patron.search(texto):
            problemas.append(
                Problema(
                    "llave",
                    archivo,
                    f"posible {nombre}. Quítala, y si era real, CÁMBIALA: el historial de git conserva lo anterior.",
                )
            )
    return problemas


def revisar_marcas(archivo: str, texto: str) -> list[Problema]:
    problemas = [
        Problema(
            "marcas",
            archivo,
            f"marca de trabajo sin resolver en el bloque inicial (title:): {m.group(0)}",
        )
        for m in MARCAS.finditer(sin_comentarios_yaml(front_matter(texto)))
    ]
    cuerpo = re.sub(r"```.*?```", "", quitar_front_matter(texto) + "\n", flags=re.S)
    cuerpo = re.sub(r"<!--.*?-->", "", cuerpo, flags=re.S)
    problemas += [
        Problema("marcas", archivo, f"marca de trabajo sin resolver: {m.group(0)}")
        for m in MARCAS.finditer(cuerpo)
    ]
    return problemas


def revisar_config(raiz: Path) -> list[Problema]:
    """_config.yml (title: y description:) se publica: marcas, teléfonos, correos, domicilios y llaves.

    Si el archivo no existe no se avisa: GitHub Pages funciona sin él.
    """
    nombre = "_config.yml"
    texto = leer(raiz / nombre)
    if not texto.strip():
        return []
    limpio = sin_comentarios_yaml(texto)
    problemas = [
        Problema(
            "marcas",
            nombre,
            f"marca de trabajo sin resolver en _config.yml: {m.group(0)}",
        )
        for m in MARCAS.finditer(limpio)
    ]
    problemas += revisar_telefonos(nombre, limpio)
    problemas += revisar_correos(nombre, limpio)
    problemas += revisar_domicilios(nombre, limpio)
    problemas += revisar_llaves(nombre, texto)
    return problemas


def existe_destino(raiz: Path, origen: Path, destino: str) -> bool:
    destino = destino.split("#", 1)[0].split("?", 1)[0]
    if not destino:
        return True
    base = raiz if destino.startswith("/") else origen.parent
    ruta = (base / destino.lstrip("/")).resolve()
    candidatos = [ruta]
    if destino.endswith("/") or ruta.is_dir():
        candidatos += [ruta / "index.md", ruta / "README.md", ruta / "index.html"]
    if ruta.suffix == ".html":
        candidatos.append(ruta.with_suffix(".md"))
    if ruta.suffix == "" and not ruta.is_dir():
        candidatos += [ruta.with_suffix(".md"), ruta.with_suffix(".html")]
    return any(c.exists() for c in candidatos)


def revisar_enlaces(raiz: Path, archivo: Path, texto: str) -> list[Problema]:
    problemas = []
    for destino in ENLACE_MD.findall(re.sub(r"```.*?```", "", texto, flags=re.S)):
        if re.match(r"(?i)^(https?:|mailto:|tel:|//|#)", destino):
            continue
        if not existe_destino(raiz, archivo, destino):
            problemas.append(
                Problema("enlace", str(archivo.relative_to(raiz)), f"enlace local roto: {destino}")
            )
    return problemas


def tiene_enlace_de_idioma(texto: str, idioma: str) -> bool:
    if idioma == "es":
        return bool(re.search(r"\]\((?:/en/?|en/|\./en/|\.\./en/)(?:index\.html)?\)", texto))
    return bool(re.search(r"\]\((?:/|\.\./|\.\./index\.html|/index\.html)\)", texto))


def verificar(raiz: Path) -> list[Problema]:
    raiz = raiz.resolve()
    problemas: list[Problema] = []
    conteo: dict[str, int] = {}
    for idioma, ruta in PAGINAS.items():
        archivo = raiz / ruta
        texto = leer(archivo)
        nombre = str(ruta).replace("\\", "/")
        if not texto.strip():
            problemas.append(Problema("paginas", nombre, "falta la página o está vacía"))
            continue
        conteo[idioma] = len(secciones(texto))
        if not tiene_enlace_de_idioma(texto, idioma):
            destino = "[English](/en/)" if idioma == "es" else "[Español](/)"
            problemas.append(Problema("paridad", nombre, f"falta el enlace de cambio de idioma, por ejemplo {destino}"))
        problemas += revisar_marcas(nombre, texto)
        problemas += revisar_telefonos(nombre, texto)
        problemas += revisar_correos(nombre, texto)
        problemas += revisar_domicilios(nombre, texto)
        problemas += revisar_llaves(nombre, texto)
        problemas += revisar_enlaces(raiz, archivo, texto)
    if len(conteo) == 2 and conteo["es"] != conteo["en"]:
        problemas.append(
            Problema(
                "paridad",
                "index.md / en/index.md",
                f"las secciones no coinciden: español {conteo['es']} e inglés {conteo['en']}. Cada idioma debe decir lo mismo.",
            )
        )
    problemas += revisar_config(raiz)
    # El archivo de límites de privacidad no debe estar en el repositorio.
    for priv in sorted(raiz.rglob("privado-NO-SUBIR*")):
        problemas.append(Problema("privacidad", str(priv.relative_to(raiz)).replace("\\", "/"), "este archivo es privado y NO debe estar en el repositorio: sácalo de la carpeta que subes"))
    # Revisión adicional: el resto de archivos de texto del portafolio también es público.
    for extra in sorted(list(raiz.glob("portafolio-ia/**/*.md")) + list(raiz.glob("proyecto/**/*.md"))):
        nombre = str(extra.relative_to(raiz)).replace("\\", "/")
        texto = leer(extra)
        problemas += revisar_marcas(nombre, texto)
        problemas += revisar_telefonos(nombre, texto)
        problemas += revisar_correos(nombre, texto)
        problemas += revisar_domicilios(nombre, texto)
        problemas += revisar_llaves(nombre, texto)
        problemas += revisar_enlaces(raiz, extra, texto)
    problemas += revisar_ficha_proyecto(raiz)
    return problemas


FICHA_SECCIONES = ["Proyecto elegido", "Problema", "Usuario", "Criterio de éxito"]
# Textos que significan «aún no lo sé»: en estas cuatro secciones cuentan como pendiente.
# («Datos y límites» y «Capas que usarás» no se revisan aquí; «Capas» puede esperar al Día 4.)
PENDIENTE = re.compile(r"(?i)^[\s*_«»\"'.\-–]*(?:sin definir|pendiente|por definir)[\s*_«»\"'.\-–]*$")


def revisar_ficha_proyecto(raiz: Path) -> list[Problema]:
    """Lab 1 (v4): proyecto/ficha-proyecto.md debe existir y tener las cuatro secciones con contenido."""
    nombre = "proyecto/ficha-proyecto.md"
    texto = leer(raiz / nombre)
    if not texto.strip():
        return [Problema("proyecto", nombre, "falta la ficha del proyecto o está vacía")]
    problemas: list[Problema] = []
    cuerpo = quitar_front_matter(texto)
    for sec in FICHA_SECCIONES:
        m = re.search(rf"(?im)^##\s+{re.escape(sec)}\s*$", cuerpo)
        if not m:
            problemas.append(Problema("proyecto", nombre, f"falta la sección «## {sec}»"))
            continue
        resto = cuerpo[m.end():]
        sig = re.search(r"(?m)^##\s", resto)
        contenido = (resto[: sig.start()] if sig else resto).strip()
        contenido = re.sub(r"<!--.*?-->", "", contenido, flags=re.S).strip()
        if PENDIENTE.match(contenido):
            problemas.append(
                Problema(
                    "proyecto",
                    nombre,
                    f"la sección «{sec}» sigue en «Sin definir»: escribe tu borrador final "
                    "(solo «Capas que usarás» puede esperar al Día 4)",
                )
            )
        elif len(contenido) < 15:
            problemas.append(Problema("proyecto", nombre, f"la sección «{sec}» está vacía o muy corta"))
    return problemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revisa un sitio bilingüe antes de publicarlo.")
    parser.add_argument("--raiz", default=".", help="raíz del repositorio del sitio (por defecto, la carpeta actual)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    problemas = verificar(Path(args.raiz))
    if problemas:
        print("REVISA ANTES DE PUBLICAR:")
        for p in problemas:
            print(" -", p)
        print(f"\n{len(problemas)} hallazgo(s). Recuerda: esta revisión es heurística; la revisión humana es obligatoria.")
        return 1
    print("Todo en orden según las reglas automáticas. Haz ahora tu revisión de privacidad humana.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
