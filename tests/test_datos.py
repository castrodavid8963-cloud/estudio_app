import json
import os
import unittest

import database as db
import respaldo
from tests import TMP
from tests.utiles import registrar_libro, crear_pdf


class BaseDeDatos(unittest.TestCase):
    def setUp(self):
        with db.obtener_conexion() as c:           # cada prueba parte sin tarjetas
            c.execute("DELETE FROM tarjetas")
            c.execute("DELETE FROM repasos")

    def test_la_bd_esta_en_la_carpeta_temporal(self):
        self.assertTrue(db.DB_NAME.startswith(TMP))

    def test_tarjetas_sin_duplicados_y_limite_diario(self):
        rid = registrar_libro(crear_pdf("t1.pdf", ["hola"]))
        lote = [{"pregunta": f"¿Pregunta número {i}?", "respuesta": f"Respuesta {i}"} for i in range(15)]
        self.assertEqual(db.agregar_tarjetas(rid, 1, lote, "ia"), 15)
        self.assertEqual(db.agregar_tarjetas(rid, 1, lote, "ia"), 0)           # no repite
        pendientes = db.tarjetas_pendientes(rid)
        self.assertEqual(len(pendientes), db.limite_nuevas())                   # solo entran N nuevas por día

    def test_repasar_reprograma_la_tarjeta(self):
        rid = registrar_libro(crear_pdf("t2.pdf", ["hola"]))
        db.agregar_tarjetas(rid, 1, [{"pregunta": "¿Qué es la pila?", "respuesta": "LIFO"}], "manual")
        t = db.tarjetas_pendientes(rid)[0]
        nuevo = db.registrar_repaso(t["id"], 3)
        self.assertGreaterEqual(nuevo["intervalo"], 1)
        self.assertEqual(db.tarjetas_pendientes(rid), [])                       # ya no está pendiente hoy

    def test_quiz_guarda_puntaje(self):
        rid = registrar_libro(crear_pdf("t3.pdf", ["hola"]))
        qs = [{"pregunta": "¿a?", "opciones": ["x", "y", "z"], "correcta": 0, "elegida": 0, "explicacion": ""},
              {"pregunta": "¿b?", "opciones": ["x", "y", "z"], "correcta": 1, "elegida": 2, "explicacion": ""}]
        db.guardar_quiz(rid, "Prueba", qs)
        q = db.listar_quizzes(1)[0]
        self.assertEqual((q["total"], q["aciertos"]), (2, 1))

    def test_mini_proyectos_sin_repetir_y_marcables(self):
        p = [{"titulo": "Agenda de contactos", "descripcion": "CLI"}]
        self.assertEqual(db.agregar_mini_proyectos("python", 0, p), 1)
        self.assertEqual(db.agregar_mini_proyectos("python", 0, p), 0)
        pid = db.listar_mini_proyectos("python")[0]["id"]
        db.marcar_mini_proyecto(pid, True)
        self.assertEqual(db.listar_mini_proyectos("python")[0]["hecho"], 1)

    def test_meta_de_ruta(self):
        db.guardar_meta_ruta("web", "2027-01-01")
        self.assertEqual(db.obtener_meta_ruta("web"), "2027-01-01")
        db.guardar_meta_ruta("web", None)
        self.assertIsNone(db.obtener_meta_ruta("web"))


class Respaldo(unittest.TestCase):
    def setUp(self):
        self.carpeta = os.path.join(TMP, "respaldos")

    def test_crear_y_restaurar_devuelve_los_datos(self):
        rid = registrar_libro(crear_pdf("r1.pdf", ["hola"]))
        db.agregar_tarjetas(rid, 1, [{"pregunta": "¿Dato que debe sobrevivir?", "respuesta": "Sí"}], "manual")
        z = respaldo.crear_respaldo(db.DB_NAME, self.carpeta)
        self.assertGreater(respaldo.leer_manifiesto(z)["contenido"]["tarjetas"], 0)
        antes = len(db.listar_tarjetas())
        db.borrar_tarjeta(db.listar_tarjetas()[0]["id"])                        # «desastre»
        self.assertEqual(len(db.listar_tarjetas()), antes - 1)
        seguridad = respaldo.restaurar(z, db.DB_NAME)
        self.assertEqual(len(db.listar_tarjetas()), antes)
        self.assertTrue(os.path.exists(seguridad))                              # copia de la BD previa

    def test_rechaza_archivos_que_no_son_respaldos(self):
        falso = os.path.join(TMP, "falso.zip")
        with open(falso, "wb") as f:
            f.write(b"esto no es un zip")
        with self.assertRaises(ValueError):
            respaldo.restaurar(falso, db.DB_NAME)

    def test_rotar_conserva_los_mas_recientes(self):
        from datetime import datetime, timedelta
        carpeta = os.path.join(TMP, "rot")
        base = datetime(2026, 1, 1)
        for i in range(5):
            respaldo.crear_respaldo(db.DB_NAME, carpeta, base + timedelta(days=i))
        borrados = respaldo.rotar(carpeta, 2)
        self.assertEqual(len(borrados), 3)
        self.assertEqual(len(respaldo.listar_respaldos(carpeta)), 2)
        self.assertEqual(respaldo.dias_desde_ultimo(carpeta, base + timedelta(days=10)), 6)

    def test_exportaciones(self):
        json_ruta, csv_ruta = os.path.join(TMP, "todo.json"), os.path.join(TMP, "t.csv")
        cuentas = respaldo.exportar_json(db.DB_NAME, json_ruta)
        self.assertIn("tarjetas", cuentas)
        with open(json_ruta, encoding="utf-8") as f:
            self.assertIn("notas", json.load(f))
        self.assertGreaterEqual(respaldo.exportar_tarjetas_csv(db.DB_NAME, csv_ruta), 1)


if __name__ == "__main__":
    unittest.main()
