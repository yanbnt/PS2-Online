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

Rode o **`Instalar PS2 Online.exe`**. Ele instala o app, os atalhos e o driver ViGEmBus, que só é necessário para hospedar.

Para rodar a partir do código-fonte: instale o Python 3.11 ou mais novo e dê dois cliques em **`Iniciar PS2 Online.bat`**.

## Host

1. Abra a tela **Início** e confira se está tudo ✓. Se faltar algo, os botões ao lado de cada item corrigem: configurar as portas no PCSX2, instalar o driver etc.
2. Em **Hospedar**, escolha o jogo, defina uma senha (opcional) e clique em **Abrir sala**. Na primeira vez, permita o acesso no aviso do firewall do Windows. A porta é aberta no roteador automaticamente (UPnP).
3. Clique em **Copiar convite** e mande o código `PS2-…` para os amigos.
4. Quando alguém tentar entrar, aparece **"Fulano quer entrar — Aceitar / Recusar"**.
5. Clique em **Abrir jogo no PCSX2** e deixe a janela visível, sem minimizar.

A tela **Controles** mostra ao vivo o seu controle e o de cada amigo, para conferir se os comandos estão chegando.

Fechar o PS2 Online encerra tudo: a sala, a porta no roteador e a conexão dos amigos, que recebem o aviso "O host fechou a sala".

## Convidado

Copie o convite que o host mandou e abra o PS2 Online. Ele detecta o convite e pergunta se você quer entrar. Também dá para colar o código na tela **Entrar**. Atalhos na janela do jogo:

- **F11:** tela cheia
- **F1:** estatísticas (ping, fps, banda)

Para jogar pelo teclado, veja o mapa de teclas na própria aba.

## Conexão pela internet

- **Automático (UPnP):** ao abrir a sala, o app abre a porta no roteador e coloca o IP dele no convite. Ao fechar o app, a porta é fechada.
- **CGNAT:** se o IP do roteador começar com 100.64 a 100.127, o convite só funciona para amigos da **mesma operadora**. O app avisa quando isso acontece.
- **Para qualquer amigo:** todos entram na mesma rede do **Radmin VPN** ou do **Tailscale**, que funcionam mesmo com CGNAT. O convite passa a usar o IP da VPN automaticamente.
- **Segurança:** o convite leva a senha, então mande só para quem vai jogar. A aprovação de cada jogador e o bloqueio de IP após 5 senhas erradas (por 10 minutos) protegem mesmo que o convite vaze.

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
