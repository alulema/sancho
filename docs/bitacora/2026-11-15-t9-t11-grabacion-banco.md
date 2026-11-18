# Bitácora — 2026-11-15 — Grabación, reproducción y banco de evaluación

- **Etapa:** E0
- **Tareas de la spec:** T9 y T11

## Qué se intentó

1. **Corrección previa: la ventana del saludo se mide con el `ts` de los eventos.** `grabaciones.md` exige que el orquestador calcule sus ventanas con el `ts` de los eventos y no con su reloj local, para que una reproducción decida lo mismo. El `Greeter` de T7 usaba el reloj monotónico; ahora usa `envelope.ts`. Un evento que llega fuera de orden (con `ts` anterior al último saludo) cuenta como dentro de la ventana.
2. **Suscripción y publicación crudas en `BusService`:**
   - `subscribe_raw` entrega los bytes tal cual, también los mensajes inválidos. Lo necesita el grabador, que debe guardar todo lo que cruza el bus.
   - `publish_raw` publica bytes sin validar. Solo lo pueden usar los roles que no son servicios (`replay`, `eval`); el ACL del broker sigue aplicando.
3. **Grabador (`python -m sim.recorder`, rol `recorder`):** escribe cada mensaje como una línea JSONL del contrato `grabaciones.md` v0.1, con `t_ms` relativo al inicio. Un objeto JSON va en `message` (aunque no sea un sobre válido); cualquier otra cosa, en `raw`. `make sim` ahora deja también `recording.jsonl`.
4. **Reproducción (`python -m sim.replay`, rol `replay`):** publica solo los eventos del cuerpo no retenidos (`sancho/body/+/evt/#`), respeta los tiempos relativos, desplaza todos los `ts` con un mismo desfase y cambia `source` a `replay`. Las líneas `raw` se publican sin tocar.
5. **Comparación (`make replay REC=…`, `python -m sim.rerun`):** arranca un broker limpio y un orquestador nuevo, reproduce la grabación y compara sus trazas de decisión con las originales: mismo orden, `name`, `decision` e `inputs.message_ids`.
6. **Banco (`make bench`, `python -m eval`):** cada caso de `eval/cases/` corre con broker, orquestador y cuerpo simulado nuevos; el runner (rol `eval`) ejecuta `when`, observa `sancho/#` y verifica `expect` y `forbid`. Los resultados van a `eval/results/`. Las reglas que el contrato no fijaba quedan en ADR-0015 y en `casos-banco.md` v0.3.
7. **Casos:** los cinco que pide la spec, y uno más (`e0-invalid-payload-not-greeted`): una entrada con `confidence: 1.7` no se saluda porque la validación la rechaza.

## Qué se midió

En el Nano (modo 5 W), con el broker del contenedor de pruebas:

| Prueba | Resultado |
|---|---|
| `python -m sim` (guion `dos-entradas.yaml`) | Sesión de 11 líneas grabada; el orquestador tarda unos 7,8 s en arrancar |
| `python -m sim.rerun` de esa sesión | 6 mensajes reproducidos, mismas 2 decisiones |
| `python -m eval --no-save` | 6/6 casos pasan; cada caso dura entre 9 y 21 s y el banco 84 s, casi todo el arranque de los componentes |

En el NUC (x86_64), 2026-11-17, broker en contenedor:

| Prueba | Resultado |
|---|---|
| `make test` y lint | 260 pasan en 86 s; `ruff check` y `ruff format --check` limpios |
| `make replay` de la sesión grabada en el Nano | 6 mensajes reproducidos, mismas 2 decisiones (`say_greeting` y `ignore`, «greeted 5.0 s ago»). **Criterio de T9 cumplido:** grabada en ARM64, reproducida en x86_64 |
| `make bench` | 6/6 casos pasan en 35 s (entre 3,6 y 9,8 s por caso) |

## Qué falló y por qué

- **El orquestador de T7 incumplía el contrato de grabaciones.** Medía la ventana con su reloj, así que una reproducción días después habría decidido lo mismo solo por casualidad. Se detectó al escribir la reproducción, antes de que existiera una prueba que lo atrapara; ahora hay dos.
- **Esperaba 4 mensajes reproducidos y fueron 6.** `speech/evt/status` también es un evento del cuerpo, y la reproducción lo publica. Es lo que dice el contrato; la prueba estaba mal.
- **Carrera al esperar que un componente esté en línea.** El instante desde el que se buscaba el `online` se tomaba después de lanzar el proceso, y un arranque rápido se perdía. Ahora se toma antes.
- **Ruido en los logs del banco.** El observador validado registraba como «rechazado» cada mensaje inválido que el propio caso inyecta. Ahora usa un logger silencioso; el rechazo que importa es el del orquestador, y ese sí aparece en su log.
- **La NUC se apagó a mitad de la sesión** (se apaga cada día), así que la primera validación se hizo en el Nano. Al volver tenía otra IP (192.168.0.120 por DHCP); la 192.168.0.118 era ya de otro equipo y rechazaba SSH. Se confirmó que era la NUC comparando sus llaves de host con las guardadas.
- **Una prueba del broker contaba mensajes ajenos.** Al suscribirse a `sancho/#` en el broker compartido de las pruebas recibía los *health* retenidos de pruebas anteriores. En el Mac no se vio porque esas pruebas se saltan sin broker. La prueba ahora se suscribe a `sancho/body/#`.

## Supuestos confirmados o refutados

Ninguno de §18.

## Decisiones tomadas

- **ADR-0015:** estado limpio con un broker por caso; `expect.count` es un mínimo y `forbid.count_gt` un máximo; los componentes son `brain` y `body`; una `given.config` inválida es un `error` del caso, no un `fail` del sistema.
- `eval/` está en `PROTECTED_PATHS`; T11 pide explícitamente crear allí el runner y los casos.

## Pendientes para la próxima sesión

- Grabar una sesión con el cuerpo real cuando exista (T6) y reproducirla en el NUC.
- T10 (latencia de punta a punta en el Nano) y T12.

## Notas para artículos

- Grabar y reproducir obliga a que el cerebro no tenga reloj propio: todo el tiempo que importa viaja en los mensajes.
- Separar «debe pasar» (`expect`, mínimo) de «no debe pasar» (`forbid`, máximo) hace que cada caso diga exactamente lo que verifica.
