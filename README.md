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

## Siguiente paso recomendado
1. Implementar la API local real en el daemon (`/ha/v1/...`).
2. Probar pairing local manual con Home Assistant.
3. Completar refresh de `input_sources` y mapping de comandos.
