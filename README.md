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

- **Host:** feche o PCSX2 e clique em **Configurar portas no PCSX2**. Depois clique em **Abrir sala**, abra o jogo e passe o IP para os amigos.
- **Convidado:** na aba **Entrar**, preencha IP, porta e senha e clique em **Conectar**.
- **Conexão pela internet:** use **Radmin VPN**, **Tailscale** ou **ZeroTier**, que funcionam até com CGNAT, ou abra a porta TCP 27900 no roteador.

## Recursos

- Vídeo **H.264** com baixa latência (x264, NVENC, QuickSync ou AMF) ou JPEG
- Áudio do PC do host (loopback WASAPI)
- Até **4 jogadores**, com multitap
- Vibração do controle repassada ao convidado
- Controle **XInput** ou **teclado** no convidado
- Configuração automática das portas no `PCSX2.ini`, com backup
- Senha na sala e bloqueio de IP após tentativas erradas
- Ícone na bandeja do sistema

## Desenvolvimento

Requer Windows e Python 3.11 ou mais novo.

```powershell
pip install -r requirements.txt
python app.py
```

| Arquivo | Função |
|---|---|
| `app.py` | Interface (PySide6) e bandeja do sistema |
| `host.py` | Captura da janela, codificação de vídeo, áudio e controles virtuais |
| `guest.py` | Decodificação, áudio, XInput e teclado |
| `pcsx2.py` | `PCSX2.ini`, lista de jogos e localização da janela |
| `protocol.py` | Protocolo TCP |
| `xinput.py` | Controles XInput (ctypes) |
| `installer/installer.py` | Instalador (tkinter) |
| `build.ps1` | Gera o app e o instalador com PyInstaller |
| `tests/e2e_test.py` | Teste ponta a ponta: host e convidado no mesmo PC |

Para gerar o instalador:

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

O app tem um autoteste embutido: `"PS2 Online.exe" --selftest resultado.txt`.
