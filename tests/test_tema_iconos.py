import re
import unittest

import tema
import iconos
from iconos_codigos import CODIGOS

CLAVES = set(tema.TEMAS["Medianoche"])


def luminancia(hex_):
    def canal(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(hex_[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class Temas(unittest.TestCase):
    def test_todos_los_temas_tienen_los_mismos_colores_validos(self):
        for nombre, p in tema.TEMAS.items():
            self.assertEqual(set(p), CLAVES, nombre)
            for k, v in p.items():
                if k != "modo":
                    self.assertRegex(v, r"^#[0-9a-fA-F]{6}$", f"{nombre}.{k}")
            self.assertIn(p["modo"], ("Dark", "Light"))

    def test_el_texto_se_lee_sobre_el_fondo(self):
        for nombre, p in tema.TEMAS.items():
            self.assertGreaterEqual(contraste(p["texto"], p["fondo"]), 7, nombre)
            self.assertGreaterEqual(contraste(p["texto"], p["tarjeta"]), 7, nombre)
            self.assertGreaterEqual(contraste(p["texto2"], p["tarjeta"]), 4.5, f"{nombre} texto2")
            self.assertGreaterEqual(contraste(p["sobre_acento"], p["acento"]), 3.0, f"{nombre} botón")   # texto en negrita: 3:1 basta

    def test_aplicar_cambia_la_paleta_en_el_sitio(self):
        previo = tema.TEMA_ACTUAL
        try:
            tema.aplicar("Blanco")
            self.assertEqual(tema.C["fondo"], tema.TEMAS["Blanco"]["fondo"])
            self.assertTrue(tema.es_claro())
            tema.aplicar("no existe")
            self.assertEqual(tema.TEMA_ACTUAL, tema.TEMA_POR_DEFECTO)
        finally:
            tema.aplicar(previo)

    def test_mezclar_y_texto_sobre(self):
        self.assertEqual(tema.mezclar("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(tema.texto_sobre("#ffffff"), "#0e1016")
        self.assertEqual(tema.texto_sobre("#000000"), "#ffffff")


class Iconos(unittest.TestCase):
    def test_cada_emoji_mapeado_apunta_a_un_icono_que_existe(self):
        for emoji, nombre in iconos.EMOJI_A_ICONO.items():
            self.assertIn(nombre, CODIGOS, f"{emoji} → {nombre}")

    def test_separar(self):
        self.assertEqual(iconos.separar("🎯 Plan y meta"), ("target", "Plan y meta"))
        self.assertEqual(iconos.separar("  🏠   Inicio"), ("house", "Inicio"))
        self.assertEqual(iconos.separar("⚙️ Ajustes"), ("settings", "Ajustes"))
        self.assertEqual(iconos.separar("Sin emoji"), (None, "Sin emoji"))
        self.assertEqual(iconos.separar("🦄 raro"), (None, "🦄 raro"))

    def test_la_fuente_dibuja_algo_visible(self):
        from PIL import Image, ImageDraw
        f = iconos._fuente(80)
        for nombre in ("house", "brain", "target"):
            im = Image.new("L", (100, 100), 0)
            ImageDraw.Draw(im).text((10, 10), chr(CODIGOS[nombre]), font=f, fill=255)
            self.assertIsNotNone(im.getbbox(), nombre)           # si el glifo no existiera, quedaría en blanco


if __name__ == "__main__":
    unittest.main()
