# Cómo contribuir a SnowSend

Gracias por interesarte. Este es un proyecto pequeño y con un objetivo
muy concreto: **que un Mac con Mac OS X 10.6 Snow Leopard pueda
intercambiar archivos con dispositivos modernos que usan el protocolo
LocalSend v2**.

## Reglas del proyecto (no negociables)

Estas restricciones son la razón de existir de SnowSend; los PR que las
rompan no se pueden aceptar:

1. **Solo Python 2.6/2.7 y la librería estándar de Snow Leopard.**
   Nada de `pip`, `requests`, `flask`, `PyInstaller`, `py2app` ni
   dependencias que haya que compilar.
2. **El código debe seguir funcionando en Python 3** (para poder
   probarlo en máquinas modernas y en CI).
3. **El paquete `SnowSend.app` debe seguir siendo un bundle clásico
   de 10.6** (`Contents/Info.plist`, `Contents/MacOS/launcher` ejecutable,
   `Contents/Resources/snowsend.py`).
4. **Sin código copiado de otros proyectos.** El código es original.
   Especialmente: no se acepta código de proyectos con licencia
   GPL/LGPL (por ejemplo clientes de LocalSend para iOS), porque
   cambiaría la licencia del proyecto entero.
5. **Mantener la licencia MIT** y el aviso de copyright en las copias.

## Antes de enviar un cambio

```sh
python3 -m py_compile snowsend.py
python3 tests/test_server_regression.py
python3 tests/test_send_fake_iphone.py
MODE=chunked python3 tests/test_send_fake_iphone.py
MODE=gzip python3 tests/test_send_fake_iphone.py
MODE=close python3 tests/test_send_fake_iphone.py
python3 tests/test_register_and_diagnose.py
chmod +x build_app.sh && ./build_app.sh
```

Todas las pruebas deben pasar (en CI también corre el mismo conjunto).

## Cómo reportar un fallo

Adjunta, por favor:

- La versión de SnowSend (aparece en el registro al arrancar).
- El sistema del otro dispositivo y la versión de su app LocalSend.
- **El registro completo de `~/Library/Logs/SnowSend.log`** desde el
  arranque hasta el fallo. Es lo que más ayuda: incluye el cuerpo y las
  cabeceras crudas cuando una respuesta no es JSON.
- Si el fallo es de red: ¿multicast funciona en tu red? ¿Lo mismo ocurre
  con *Escanear red*?

## Ideas bienvenidas

- Diálogo de aceptar/rechazar al recibir (ahora se acepta todo).
- Envío de texto y de carpetas.
- Icono propio para el `.app`.
- Traducción de la interfaz al inglés.
- Soporte del endpoint `/cancel` en la interfaz.
