# RemoteRelay Home Assistant Custom Component (PoC scaffold)

Estado: scaffold inicial para arrancar la PoC de Home Assistant con:
- zeroconf autodiscovery del daemon (`_remoterelay._tcp.local`)
- config flow con paso de pairing local (codigo temporal)
- entidad unica `media_player`
- `turn_on` via WoL desde Home Assistant (sin segundo dispositivo)

## Objetivo del scaffold
Este directorio deja la estructura base de la integracion para implementar el contrato definido en:
- `docs/product/home-assistant-poc-v1.md`
- `docs/architecture/adr/0011-home-assistant-custom-integration-zeroconf-local-pairing.md`
- `docs/architecture/contracts/home-assistant-remoterelay-local-bridge-v1.md`
- `api/openapi/remoterelay-local-ha.v1.yaml`

## Instalacion local (dev)
Copiar `custom_components/remoterelay` dentro de tu configuracion de Home Assistant:

`<HA_CONFIG>/custom_components/remoterelay`

## Estado de implementacion
- `manifest.json`: listo
- `config_flow.py`: zeroconf + pairing step (cliente API local)
- `api.py`: cliente local HTTP (skeleton funcional)
- `media_player.py`: entidad base y WoL via HA
- `remote.py`: entidad `remote` para flechas / home / back / info / media keys
- `button.py`: botones plug-and-play (Device page) para mando
- `select.py`: selector de input source (Device page)

## UX en Home Assistant (importante)
La integracion ya expone UI plug-and-play en la **Device page** (sin Lovelace manual) mediante:
- `media_player.remoterelay_*` -> power, volumen, mute
- `select.remoterelay_*_input_source` -> selector de sources
- `button.remoterelay_*_*` -> botones de mando (flechas, OK, Back, Home, Info, etc.)
- `remote.remoterelay_*_remote` -> entidad avanzada para automatizaciones y dashboards custom

### Limite de Home Assistant (importante)
Home Assistant **no genera automaticamente** una card visual tipo "Apple TV Remote" como Apple Home.
Para una UI tipo mando con D-pad en un dashboard, sigue siendo necesario crear una card Lovelace (manual).

### Ejemplo Lovelace (mando + sources)
> Sustituye `media_player.current_pc` y `remote.current_pc_remote` por tus entity IDs reales.

```yaml
type: vertical-stack
cards:
  - type: media-control
    entity: media_player.current_pc

  - type: grid
    columns: 3
    square: false
    cards:
      - type: button
        name: Home
        icon: mdi:home
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: home
      - type: button
        name: Up
        icon: mdi:chevron-up
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: up
      - type: button
        name: Info
        icon: mdi:information-outline
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: info
      - type: button
        name: Left
        icon: mdi:chevron-left
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: left
      - type: button
        name: OK
        icon: mdi:check-circle-outline
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: ok
      - type: button
        name: Right
        icon: mdi:chevron-right
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: right
      - type: button
        name: Back
        icon: mdi:arrow-left
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: back
      - type: button
        name: Down
        icon: mdi:chevron-down
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: down
      - type: button
        name: Play/Pause
        icon: mdi:play-pause
        tap_action:
          action: call-service
          service: remote.send_command
          target:
            entity_id: remote.current_pc_remote
          data:
            command: play_pause
```

## Siguiente paso recomendado
1. Implementar la API local real en el daemon (`/ha/v1/...`).
2. Probar pairing local manual con Home Assistant.
3. Completar refresh de `input_sources` y mapping de comandos.
