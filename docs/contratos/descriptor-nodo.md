# Contrato: descriptor de nodo — v0.1 (especificación)

> Se especifica en E0 y se implementa en E6, junto con la CA local. Ver `docs/diseno.md` §4.3.

Cada nodo (cuerpo del estudio, satélites, nodos de radio vía pasarela, actuadores) publica una ficha que lo describe.

```yaml
v: "0.1"
id: aire-cocina-01
type: environmental_sensor
firmware: 1.2.0
sensors:
  - name: co2
    unit: ppm
    range: [400, 5000]
    period_s: 30
actuators: []
safety_class: passive        # passive | harmless_actuator | physical_risk
privacy_class: none          # none | presence | audio | image
transport: wifi              # wifi | nrf24_via_gateway | lora_via_gateway
```

Un actuador se describe con comandos tipados, que el harness convierte en herramientas:

```yaml
actuators:
  - name: fan
    commands:
      - name: set_speed
        params:
          speed: { type: integer, min: 0, max: 3 }
```

## Reglas

- El descriptor es una **declaración, no una autorización**. Los permisos los fija la clase que aprueba el usuario.
- Un nodo `physical_risk` puede anunciarse, pero sus límites se definen en código y se revisan a mano; nunca se toman del descriptor.
- Los nodos `audio` o `image` heredan las reglas de privacidad de los satélites (solo eventos, LED de actividad).
- Si un nodo cambia su descriptor, vuelve a cuarentena.
- Tópicos previstos (E6): `sancho/discovery/<id>/descriptor` en cuarentena; tras la aprobación, los tópicos propios del nodo con su certificado.
