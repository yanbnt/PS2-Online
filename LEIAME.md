# PS2 Online

Jogue o **multiplayer local** de jogos de PS2 no PCSX2 **pela internet**.

O host roda o PCSX2 e joga como Jogador 1. Os convidados recebem a imagem e o som da tela do host e controlam os Jogadores 2, 3 e 4 por meio de controles virtuais de Xbox (driver ViGEmBus). É o mesmo esquema do "Remote Play Together" da Steam, mas feito para o PCSX2.

```
 CONVIDADO                                   HOST
┌──────────────┐  controle (≈60 bytes/s)  ┌───────────────────────────────┐
│ janela do    │ ───────────────────────▶ │ controle virtual Xbox (ViGEm) │
│ jogo + tecla-│                          │        ▼ SDL-1, SDL-2…        │
│ do/controle  │ ◀─────────────────────── │ PCSX2 (Pad 2/3/4)             │
└──────────────┘  vídeo H.264 + áudio     │ captura da janela + áudio     │
                                          └───────────────────────────────┘
```

## Instalação

1. Instale o **Python 3.11 ou mais novo** (python.org) e marque "Add python.exe to PATH".
2. Dê dois cliques em **`Iniciar PS2 Online.bat`**. Na primeira vez ele instala as dependências (alguns minutos).
3. **Só quem hospeda:** instale o driver **ViGEmBus** (https://github.com/nefarius/ViGEmBus/releases).

## Host

1. Feche o PCSX2. Na aba **Hospedar**, escolha o modo (2 jogadores, ou multitap para 4) e o **Nº SDL do 1º convidado**, que é a quantidade de controles físicos que você tem ligados. Depois clique em **Configurar portas no PCSX2**. Isso grava os Pads dos convidados no `PCSX2.ini` e faz um backup em `PCSX2.ini.bak-ps2online`.
2. Clique em **Abrir sala**. Na primeira vez, permita o acesso no aviso do firewall do Windows.
3. Clique em **Abrir jogo no PCSX2** e deixe a janela visível, sem minimizar.
4. Mande para os amigos o IP e a porta que aparecem na tela.

## Convidado

Na aba **Entrar**, preencha o IP, a porta e a senha e clique em **Conectar**. Atalhos na janela do jogo:

- **F11:** tela cheia
- **F1:** estatísticas (ping, fps, banda)

Para jogar pelo teclado, veja o mapa de teclas na própria aba.

## Conexão pela internet

- **Recomendado:** todos entram na mesma rede do **Radmin VPN**, do **ZeroTier** ou do **Tailscale**, e o convidado usa o IP do host nessa rede. Funciona mesmo com **CGNAT** e não deixa nenhuma porta aberta para a internet.
- **Alternativa:** o host abre a porta **TCP 27900** no roteador e passa o IP público (há um botão na interface que mostra esse IP). **Não funciona com CGNAT.** Para saber se você está atrás de CGNAT: se o IP WAN que aparece no roteador for diferente do IP público, ou começar com 100.64 a 100.127, é CGNAT.
- Com a porta aberta: defina uma senha forte e feche a sala quando não estiver jogando. Depois de 5 senhas erradas, o IP fica bloqueado por 10 minutos.

## Banda (upload do host, por convidado)

| Qualidade | Vídeo   | + áudio  |
|-----------|---------|----------|
| Leve      | 2,5 Mbps | 1,5 Mbps |
| Padrão    | 5 Mbps  | 1,5 Mbps |
| Alta      | 8 Mbps  | 1,5 Mbps |

## Arquivos

| Arquivo      | O que faz |
|--------------|-----------|
| `app.py`     | Interface (PySide6) |
| `host.py`    | Captura da janela (mss), redimensionamento/JPEG (PyAV/Qt), codificação H.264 (PyAV: x264/NVENC/QSV/AMF), áudio por loopback WASAPI, controles virtuais |
| `guest.py`   | Decodificação, reprodução de áudio, leitura de XInput e teclado |
| `pcsx2.py`   | Configuração do `PCSX2.ini`, lista de jogos, localização da janela |
| `protocol.py`| Protocolo TCP |
| `xinput.py`  | Leitura e vibração de controles XInput |

## Limitações

- O áudio transmitido é o som do PC inteiro do host. Se o host usa Discord nas caixas de som, o convidado ouve eco.
- A janela do PCSX2 precisa ficar visível no host, porque a captura é da tela.
- O convidado lê controles **XInput**. Controles de PlayStation precisam do DS4Windows ou do Steam Input.
- A senha é enviada sem criptografia. Use uma senha que você não usa em outro lugar.
