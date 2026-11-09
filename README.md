<p align="center"><img src="icon.png" width="96" alt="PS2 Online"></p>

<h1 align="center">PS2 Online</h1>
<p align="center">Jogue o <b>multiplayer local</b> do PCSX2 <b>pela internet</b>, com interface gráfica.</p>

---

O host roda o PCSX2 e joga como Jogador 1. Os convidados recebem a imagem e o som e controlam os Jogadores 2, 3 e 4 por controles virtuais de Xbox (driver ViGEmBus). Para o jogo, é como se todos estivessem no mesmo sofá.

## Baixar

Baixe o **`Instalar PS2 Online.exe`** na página de **[Releases](../../releases/latest)** e execute.

O instalador já traz tudo: o app, os atalhos e o driver de controle virtual. Não é preciso instalar Python.

> O Windows pode mostrar "O Windows protegeu o computador", porque o instalador não tem assinatura digital. Clique em **Mais informações → Executar assim mesmo**.

## Como usar

O guia completo está em **[LEIAME.md](LEIAME.md)** e na aba **Ajuda** do app. Resumo:

- **Host:** em **Hospedar**, escolha o jogo, clique em **Abrir sala** e depois em **Copiar convite**. Mande o código `PS2-…` para os amigos e aprove quem pedir para entrar.
- **Convidado:** copie o convite e abra o PS2 Online. Ele detecta o código e pergunta se você quer entrar. Também dá para colar o código na aba **Entrar**.
- **Conexão pela internet:** o app abre a porta no roteador sozinho (UPnP). Com **CGNAT**, isso só funciona entre clientes da mesma operadora; para os outros casos, usem **Radmin VPN** ou **Tailscale**, e o convite passa a usar o IP da VPN.

## Recursos

- **Chamada de voz** entre todos da sala (Opus), com mutar (F9), apertar para falar e indicador de quem está falando
- **Som do jogo sem eco:** o host transmite **só o som do PCSX2** (captura WASAPI por processo)
- **Controles ligados sozinhos:** o app descobre qual controle é do host e qual é de cada amigo e ajusta o PCSX2
- **Código de convite** com IP, porta e senha, validado na hora, e detecção automática na área de transferência
- **Aprovação** de cada jogador antes de ele entrar
- **UPnP:** abre a porta no roteador ao abrir a sala e fecha ao sair
- Tela **Controles** que mostra ao vivo os controles físicos e virtuais, com botões e analógicos animados
- Vídeo **H.264** com baixa latência (x264, NVENC, QuickSync ou AMF) ou JPEG
- Áudio do PC do host (loopback WASAPI)
- Até **4 jogadores**, com multitap, e vibração repassada ao convidado
- Controle **XInput** ou **teclado** no convidado
- Checagem do que falta (PCSX2, controles, driver, rede), com botões de correção
- Configuração automática das portas no `PCSX2.ini`, com backup
- Senha na sala e bloqueio de IP após tentativas erradas
- Interface com animações e ícone na bandeja do sistema. Fechar o app encerra tudo: a sala, a porta do roteador e a conexão.

## Desenvolvimento

Requer Windows e Python 3.11 ou mais novo.

```powershell
pip install -r requirements.txt
python app.py
```

| Arquivo | Função |
|---|---|
| `app.py` | Interface (PySide6): páginas, bandeja do sistema |
| `widgets.py` | Componentes animados: botões, cartões, toast, spinner, desenho do controle |
| `invite.py` | Código de convite `PS2-…` |
| `upnp.py` | UPnP: IP do roteador e abertura/fechamento de porta |
| `voice.py` | Chamada de voz: microfone, Opus, mixagem, apertar para falar |
| `procloop.py` | Captura do som de um processo (o PCSX2) via WASAPI process loopback (comtypes) |
| `host.py` | Captura da janela, codificação de vídeo, áudio e controles virtuais |
| `guest.py` | Decodificação, áudio, XInput e teclado |
| `pcsx2.py` | `PCSX2.ini`, lista de jogos e localização da janela |
| `protocol.py` | Protocolo TCP |
| `xinput.py` | Controles XInput (ctypes) |
| `installer/PS2Online.iss` | Instalador (Inno Setup): atalhos, driver ViGEmBus e desinstalador |
| `build.ps1` | Gera o app (PyInstaller, modo pasta) e o instalador (Inno Setup) |
| `tests/e2e_test.py` | Teste ponta a ponta: host e convidado no mesmo PC (ex.: `libx264 1280x720`) |
| `tests/voice_test.py` | Teste da chamada de voz: host + 2 convidados |
| `tests/game_audio_test.py` | Teste do som do jogo com o "PCSX2" aberto pelo app (precisa de um script que toque um tom) |

Para gerar o instalador, é preciso o [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`):

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

> Não use o PyInstaller `--onefile` para o instalador. O Windows Defender marca esse tipo de `.exe` como `Trojan:Win32/Wacatac.B!ml` (falso positivo da detecção por IA). O app em modo pasta e o instalador do Inno Setup passam limpos.

O app tem um autoteste embutido: `"PS2 Online.exe" --selftest resultado.txt`.

## Licença

O código do PS2 Online está sob a licença **[MIT](LICENSE)**: pode usar, modificar e distribuir, desde que mantenha o aviso de copyright.

O instalador inclui componentes de terceiros, cada um com a sua licença: [PySide6/Qt](https://www.qt.io/licensing/) (LGPL), [PyAV](https://github.com/PyAV-Org/PyAV)/FFmpeg (BSD/LGPL/GPL), [ViGEmBus](https://github.com/nefarius/ViGEmBus) e [vgamepad](https://github.com/yannbouteiller/vgamepad) (BSD/MIT), [mss](https://github.com/BoboTiG/python-mss) (MIT), [NumPy](https://numpy.org/) (BSD) e [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) (MIT).

O PS2 Online não inclui jogos, BIOS nem o PCSX2. Use apenas cópias que você tem o direito de usar.
