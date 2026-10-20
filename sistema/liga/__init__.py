"""Liga del torneo: calendario, ejecución, tabla, calificación y publicación.

Módulos:
- `calendario`: todos contra todos (4 partidas por pareja) y reparto en shards.
- `ejecutar`: juega las parejas y las guarda de forma atómica; reanuda.
- `tabla`: puntos y desempates (docs/calificacion.md).
- `calificacion`: calificación de los alumnos (docs/calificacion.md).
- `manifest`: hashes de las entregas, versión del motor e imagen, semilla.
- `publicar`: tabla.csv, calificaciones cifradas, resumen.md y sitio.
"""
