import unittest

import buscador
import ocr
from tests.utiles import crear_pdf, crear_pdf_escaneado, registrar_libro


class Consulta(unittest.TestCase):
    def test_prefijos_frases_y_peligros(self):
        self.assertEqual(buscador.construir_consulta("punteros"), '"punteros"*')
        self.assertEqual(buscador.construir_consulta('"memoria compartida"'), '"memoria compartida"')
        self.assertEqual(buscador.construir_consulta("a b"), '"a" AND "b"')
        self.assertIsNone(buscador.construir_consulta("   "))
        self.assertIsNotNone(buscador.construir_consulta('malo" OR * NEAR('))      # no revienta FTS5

    def test_fragmento_con_marcas(self):
        f = f"hola {buscador.MARCA_INI}mundo{buscador.MARCA_FIN} cruel"
        self.assertEqual(buscador.partir_fragmento(f), [("hola ", False), ("mundo", True), (" cruel", False)])


class Indice(unittest.TestCase):
    def test_indexar_y_buscar_con_acentos(self):
        ruta = crear_pdf("idx.pdf", ["Los punteros apuntan a memoria dinamica en el heap."] + ["relleno de la pagina"] * 2)
        rid = registrar_libro(ruta)
        buscador.inicializar()
        buscador.indexar_libro(rid, ruta, buscador.firma_archivo(ruta))
        r = buscador.buscar("punte dinámica")
        self.assertTrue(any(x[0] == rid and x[1] == 1 for x in r))
        self.assertEqual(buscador.buscar("inexistentexyz"), [])

    def test_quitar_libro_borra_sus_paginas(self):
        ruta = crear_pdf("idx2.pdf", ["texto unico zebra amarilla para borrar"] * 2)
        rid = registrar_libro(ruta)
        buscador.inicializar()
        buscador.indexar_libro(rid, ruta, buscador.firma_archivo(ruta))
        self.assertTrue(buscador.buscar("zebra"))
        buscador.quitar_libro(rid)
        self.assertFalse([x for x in buscador.buscar("zebra") if x[0] == rid])


@unittest.skipUnless(ocr.estado()["disponible"], "Tesseract no está instalado")
class OCR(unittest.TestCase):
    def test_pdf_escaneado_se_detecta_y_se_reconoce(self):
        ruta = crear_pdf_escaneado("scan.pdf", ["Hello world pointers memory", "Binary trees recursion"])
        rid = registrar_libro(ruta)
        buscador.inicializar()
        firma = buscador.firma_archivo(ruta)
        buscador.indexar_libro(rid, ruta, firma)
        self.assertTrue(buscador.estado_indice()[rid][2], "debería marcarse como escaneado")
        self.assertEqual(buscador.buscar("pointers"), [])                        # sin OCR no hay nada que buscar
        est = ocr.estado()
        self.assertTrue(buscador.ocr_libro(rid, ruta, firma, est["idioma"], est["ruta"]))
        self.assertTrue(any(x[0] == rid for x in buscador.buscar("pointers")))   # ahora sí
        self.assertFalse(buscador.estado_indice()[rid][2])
        self.assertIn("recursion", " ".join(t for _, t in buscador.textos_ocr(rid)).lower())

    def test_ocr_retoma_donde_quedo(self):
        ruta = crear_pdf_escaneado("scan2.pdf", ["First page alpha", "Second page beta"])
        rid = registrar_libro(ruta)
        buscador.inicializar()
        firma = buscador.firma_archivo(ruta)
        buscador.indexar_libro(rid, ruta, firma)
        est = ocr.estado()
        llamadas = {"n": 0}

        def parar():
            llamadas["n"] += 1
            return llamadas["n"] > 1                                             # se interrumpe tras la 1.ª página
        self.assertFalse(buscador.ocr_libro(rid, ruta, firma, est["idioma"], est["ruta"], parar))
        hechas = len(buscador.textos_ocr(rid))
        self.assertEqual(hechas, 1)
        self.assertTrue(buscador.ocr_libro(rid, ruta, firma, est["idioma"], est["ruta"]))
        self.assertEqual(len(buscador.textos_ocr(rid)), 2)


if __name__ == "__main__":
    unittest.main()
