import unittest
from datetime import date, timedelta

import repaso as rp

HOY = date(2026, 11, 9)


class Programacion(unittest.TestCase):
    def test_primera_vez_segun_calidad(self):
        t = {}
        self.assertEqual(rp.programar(t, rp.DIFICIL, HOY)["intervalo"], 1)
        self.assertEqual(rp.programar(t, rp.BIEN, HOY)["intervalo"], 1)
        self.assertEqual(rp.programar(t, rp.FACIL, HOY)["intervalo"], 3)

    def test_otra_vez_reinicia_y_cuenta_lapso(self):
        t = {"facilidad": 2.5, "intervalo": 10, "repeticiones": 4, "lapsos": 0}
        r = rp.programar(t, rp.OTRA_VEZ, HOY)
        self.assertEqual((r["intervalo"], r["repeticiones"], r["lapsos"]), (0, 0, 1))
        self.assertEqual(r["proxima"], HOY.isoformat())
        self.assertLess(r["facilidad"], 2.5)

    def test_intervalos_crecen(self):
        t = {"facilidad": 2.5, "intervalo": 0, "repeticiones": 0, "lapsos": 0}
        vistos = []
        for _ in range(5):
            r = rp.programar(t, rp.BIEN, HOY)
            vistos.append(r["intervalo"])
            t = {**t, **r}
        self.assertEqual(vistos, sorted(vistos))
        self.assertGreater(vistos[-1], vistos[0] * 3)

    def test_facilidad_nunca_baja_del_minimo(self):
        t = {"facilidad": 1.3, "intervalo": 5, "repeticiones": 3, "lapsos": 0}
        for _ in range(10):
            t = {**t, **rp.programar(t, rp.OTRA_VEZ, HOY)}
        self.assertGreaterEqual(t["facilidad"], rp.FACILIDAD_MIN)

    def test_proxima_es_hoy_mas_intervalo(self):
        r = rp.programar({"repeticiones": 1, "intervalo": 1, "facilidad": 2.5}, rp.BIEN, HOY)
        self.assertEqual(r["proxima"], (HOY + timedelta(days=r["intervalo"])).isoformat())

    def test_vista_previa_tiene_cuatro_etiquetas(self):
        v = rp.vista_previa({}, HOY)
        self.assertEqual(set(v), {0, 1, 2, 3})
        self.assertEqual(v[0], "hoy")


class Lectura(unittest.TestCase):
    def test_tarjetas_con_vallas_de_codigo(self):
        txt = '```json\n{"tarjetas": [{"pregunta": "¿Qué es un puntero?", "respuesta": "Una dirección"}]}\n```'
        self.assertEqual(len(rp.parsear_tarjetas(txt)), 1)

    def test_tarjetas_descarta_invalidas(self):
        txt = '{"tarjetas": [{"pregunta": "x", "respuesta": "y"}, {"pregunta": "¿Qué es la recursión?", "respuesta": "Auto-llamada"}]}'
        self.assertEqual(len(rp.parsear_tarjetas(txt)), 1)

    def test_tarjetas_texto_basura(self):
        self.assertEqual(rp.parsear_tarjetas("no es json"), [])

    def test_quiz_correcta_por_letra_e_indice(self):
        txt = ('{"preguntas": [{"pregunta": "¿Cuál reserva memoria?", "opciones": ["A) malloc", "B) free", "C) printf", "D) exit"], '
               '"correcta": "A"}, {"pregunta": "¿Cuál libera memoria?", "opciones": ["malloc", "free", "printf"], "correcta": 1}]}')
        q = rp.parsear_quiz(txt)
        self.assertEqual([x["correcta"] for x in q], [0, 1])
        self.assertEqual(q[0]["opciones"][0], "malloc")        # quita el «A)»

    def test_quiz_sin_correcta_valida_se_descarta(self):
        txt = '{"preguntas": [{"pregunta": "¿Algo?", "opciones": ["a", "b", "c"], "correcta": "Z"}]}'
        self.assertEqual(rp.parsear_quiz(txt), [])


if __name__ == "__main__":
    unittest.main()
