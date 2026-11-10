import unittest
from datetime import date

import plan
import tutor

HOY = date(2026, 11, 9)


class Plan(unittest.TestCase):
    def test_ritmo_sin_datos_es_estimado(self):
        self.assertEqual(plan.ritmo_paginas_hora([]), (20.0, "estimado"))

    def test_ritmo_usa_mediana_y_acota(self):
        pph, base = plan.ritmo_paginas_hora([(60, 3600), (10, 3600), (200, 7200)])
        self.assertEqual((pph, base), (60.0, "medido"))
        self.assertEqual(plan.ritmo_paginas_hora([(5000, 3600)])[0], plan.PAGINAS_HORA_MAX)

    def test_restante_respeta_avance_y_completado(self):
        self.assertEqual(plan.paginas_restantes({"estado": "En progreso", "total_paginas": 400, "avance": 0.25}), 300)
        self.assertEqual(plan.paginas_restantes({"estado": "Completado", "total_paginas": 400, "avance": 1}), 0)

    def test_proyeccion_estados(self):
        trabajo = 30 * 3600
        self.assertEqual(plan.proyeccion(trabajo, 3600, "2027-01-01", HOY)["estado"], "a_tiempo")
        self.assertEqual(plan.proyeccion(trabajo, 3600, "2026-12-09", HOY)["estado"], "justo")
        self.assertEqual(plan.proyeccion(trabajo, 3600, "2026-11-20", HOY)["estado"], "atrasado")
        self.assertEqual(plan.proyeccion(trabajo, 3600, "2026-11-01", HOY)["estado"], "vencida")
        self.assertEqual(plan.proyeccion(trabajo, 3600, None, HOY)["estado"], "sin_meta")
        self.assertEqual(plan.proyeccion(0, 3600, None, HOY)["estado"], "completa")

    def test_calor_niveles_y_rejilla(self):
        self.assertEqual([plan.nivel_calor(s, 1800) for s in (0, 100, 600, 1000, 1800)], [0, 1, 2, 3, 4])
        g = plan.rejilla_calor({"2026-11-09": 1800}, 1800, 10, HOY)
        self.assertEqual(len(g), 10)
        self.assertEqual(g[-1][0], ("2026-11-09", 1800, 4))      # el 9/nov/2026 es lunes
        self.assertIsNone(g[-1][1])                              # el martes todavía no llega

    def test_proyectos_ia(self):
        txt = '{"proyectos": [{"titulo": "Agenda de contactos", "descripcion": "CLI"}, {"titulo": "x"}]}'
        self.assertEqual([p["titulo"] for p in plan.parsear_proyectos(txt)], ["Agenda de contactos"])


class Tutor(unittest.TestCase):
    def test_citas_se_enlazan(self):
        t = tutor.partir_con_citas("Ver (p. 12) y págs. 3, 5 y 9; también pp. 4–6.", 120)
        paginas = [p for _, p in t if p]
        self.assertEqual(paginas, [12, 3, 5, 9, 4])

    def test_no_enlaza_falsos_positivos(self):
        self.assertEqual([p for _, p in tutor.partir_con_citas("porque 12 libros", 120) if p], [])
        self.assertEqual([p for _, p in tutor.partir_con_citas("(p. 999)", 120) if p], [])

    def test_fuentes(self):
        self.assertEqual(tutor.etiqueta_fuentes([5, 3, 3, 40]), "Fuentes: p. 3, 5, 40")
        self.assertEqual(tutor.etiqueta_fuentes([]), "")


if __name__ == "__main__":
    unittest.main()
