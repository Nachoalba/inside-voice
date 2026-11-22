<p align="center"><img src="assets/banner.png" alt="Inside Voice - Chitón, que te oyen." width="720"></p>

[English](README.md) · **Español**

Inside Voice vigila el nivel de tu micrófono mientras hablas por el PC (juegos, Discord, llamadas) y te avisa
**visualmente** cuando subes la voz: aparece un borde alrededor de la pantalla que se hace más intenso cuanto
más fuerte hablas. Como el aviso es visual, no molesta ni a tu juego ni a tu chat de voz.

> *Chitón, que te oyen.*

## Cómo se ve el aviso

<img src="assets/preview.png" alt="Simulación de los niveles de aviso 1, 2 y 3">

*(Simulación. El borde real se dibuja sobre tu pantalla; su aspecto es totalmente configurable.)*

## Qué hace

- **Aviso progresivo**: de 2 a 4 niveles. Cuanto más alto hablas, más grueso, opaco y rápido es el borde.
- **Filtro de voz**: reacciona solo a la *voz*; ignora teclado, clics, portazos y ventiladores.
- **Calibración guiada** en una ventana: hablas normal y luego más alto, y los niveles se ajustan solos.
- **Multimonitor**: eliges en qué monitores sale el aviso (funciona con resoluciones distintas; el grosor se
  escala por monitor). El botón *Identificar monitores* muestra un número en cada pantalla.
- **Aspecto totalmente configurable**: color por nivel, grosor, opacidad, velocidad de parpadeo y estilo
  (resplandor suave, línea sólida, degradado, solo esquinas o un marco PNG propio). Vista previa en directo.
- **Modo noche**: un horario (horas y días) con un umbral más bajo, para que de noche el aviso salga antes.
- **Sonido suave opcional** (desactivado por defecto).
- Interfaz en **español e inglés** (sigue el idioma de Windows o lo eliges tú).
- **Ligero**: solo mide el nivel del micrófono; el borde se dibuja una vez por aviso y mientras parpadea solo
  cambia su transparencia. Sin aviso no se dibuja nada. La pestaña *General* muestra la CPU y la RAM que gasta
  el propio programa.
- **Privado**: el audio no se guarda ni se envía a ningún sitio; el programa no tiene código de red.

## Instalación (Windows 10/11)

Descarga `InsideVoice-Setup-<versión>.exe` desde la página de [Releases](../../releases) (o desde los
*Artifacts* de la última ejecución correcta en la pestaña [Actions](../../actions)), ejecútalo y sigue el
asistente. También hay un `.zip` portátil.

La primera vez se abre un asistente de calibración. Después queda en la bandeja del sistema (el fantasmita junto
al reloj): doble clic para abrir la configuración, clic derecho para pausar, probar el aviso o salir.

### Conviene saber

- El micrófono se abre en **modo compartido**, así que Discord, el juego o un asistente de voz con IA siguen
  funcionando a la vez.
- Los juegos en *pantalla completa exclusiva* ocultan cualquier superposición. Usa pantalla completa sin bordes
  (*borderless*) o en ventana para ver el borde.
- El borde es una ventana independiente que deja pasar los clics: no inyecta nada en el juego.
- Vuelve a calibrar si cambias de micrófono, su ganancia o la distancia a él.
- El parpadeo está limitado (el brusco, a 3 destellos por segundo como máximo). Elige *Sin parpadeo* si los
  destellos te molestan.

## Compilarlo tú mismo

Necesita Windows y Python 3.10+ (64 bits):

```bat
build.bat
```

Instala las dependencias, ejecuta los tests y una autocomprobación, genera `dist\InsideVoice\InsideVoice.exe`
con PyInstaller y, si tienes [Inno Setup 6](https://jrsoftware.org/isinfo.php), el instalador en
`dist-installer\`.

Para desarrollar: `pip install -r requirements-dev.txt`, `python -m inside_voice`, `python -m pytest`.
`python -m inside_voice --selftest` comprueba traducciones, dibujo, monitores, ventanas del aviso y la ventana de
configuración sin necesitar micrófono.

GitHub Actions (`.github/workflows/build.yml`) hace lo mismo en cada subida y publica el instalador como release
con el nombre de la versión de `inside_voice/__init__.py` (súbela para publicar una versión nueva).

## Cómo funciona

Mira el esquema y la tabla de módulos en el [README en inglés](README.md#how-it-works).

## Hoja de ruta

Mira [docs/ROADMAP.md](docs/ROADMAP.md): temas por juego con marcos y animaciones propios, y más.

## Licencia

Inside Voice es software libre, publicado bajo la **Licencia Pública General de GNU v3.0 o posterior** (ver [LICENSE](LICENSE)).
Puedes usarlo, estudiarlo, compartirlo y modificarlo; si distribuyes una versión modificada debe mantener la misma
licencia y su código fuente disponible.

## Política de firma de código

Windows puede mostrar el aviso de *SmartScreen* ("Windows protegió su PC") con descargas nuevas sin firmar. Pulsa
**Más información → Ejecutar de todos modos**. Las versiones las compila automáticamente GitHub Actions a partir del
código de este repositorio y no contienen nada más. Se está solicitando la firma gratuita a la SignPath Foundation;
esta sección describirá la política de firma cuando se apruebe.

## Apoyo

Inside Voice es gratis. Si te resulta útil, puedes apoyar su desarrollo desde la pestaña *General → Acerca de* de la
app (botón del café, cuando se active).
