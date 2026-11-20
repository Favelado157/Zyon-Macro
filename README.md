# GhosttzzKBot

Gravador de movimentos, cliques e rolagem do mouse para Windows 11.

## Instalação

Baixe `GhosttzzKBot-Windows11.zip`, extraia os arquivos e execute `GhosttzzKBot-Setup.exe`. Abra o painel pelo menu Iniciar após a instalação. [Versões no GitHub](https://github.com/Favelado157/Ghostt_Macro/releases)

| Ação | Atalho inicial |
| --- | --- |
| Gravar | F5 |
| Pausar ou retomar | F6 |
| Reproduzir | F7 |
| Parar | F8 |
| Mostrar ou ocultar a janela | Ctrl + Alt + G |
| Abrir pasta de gravações | Ctrl + Alt + F |
| Destacar configurações do painel | Ctrl + Alt + C |

Edite os quatro atalhos principais em **Atalhos de Teclado**. Use **Temas** para trocar as imagens ou salve `banner.png`, `cabecalho.png`, `lateral.png`, `icone.png` e `icone.ico` em `%LOCALAPPDATA%\GhosttzzKBot\config`. Reabra o painel para aplicar as imagens. O ícone dos atalhos de instalação vem de `app/assets/GhosttzzKBot.ico`.

## Gravação de teclado

Em **Configurações**, ative **Gravar teclas digitadas** antes de iniciar. A opção vem desligada. Durante a gravação, o painel sinaliza a captura de teclado no rodapé. A macro mantém a ordem e os intervalos entre mouse e teclado, inclusive teclas especiais, modificadores e repetições. Os atalhos que acionam o painel são removidos da captura.

Use o mesmo layout de teclado na reprodução. Senhas digitadas durante uma gravação ativa podem aparecer no JSON exportado. Pause ou pare a gravação antes de digitar dados sensíveis.

## Compilação e atualizações

A versão 1.2.0 migra a consulta de atualizações para este repositório. Se você usa a versão 1.1.0, instale a nova versão pelo link da página de Releases. Configurações e gravações ficam na mesma pasta de dados.

Em um computador Windows com Python 3.12 e Inno Setup 6 (ou Chocolatey), execute `app\build_windows.bat`. O instalador sai em `app\installer`. A publicação de uma tag `vMAJOR.MINOR.PATCH` dispara a compilação e a publicação do ZIP no GitHub Actions. Antes de publicar, alinhe a versão em `app/ghosttzzkbot.py` e `app/installer.iss`.

O aplicativo consulta a versão pública no GitHub ao iniciar, sem conta ou token. O aviso aparece quando existe uma versão mais recente com o ZIP do Windows publicado. A partir da versão 1.4.0, ao confirmar, o painel baixa o ZIP, verifica o SHA-256 publicado no GitHub e executa o instalador. O painel fecha para aplicar a atualização e reabre ao terminar. Instale a versão 1.4.0 uma vez pelo ZIP se você estiver usando uma versão anterior. A engrenagem no canto superior direito destaca as configurações no painel. O botão **Avançado** abre a pasta de configuração. Para instalar pela configuração local, coloque o novo instalador na pasta `config` e crie `config/update.json` com, por exemplo, `{"version":"1.5.0","installer":"GhosttzzKBot-Setup.exe"}`. A versão precisa ser maior que a instalada. O app pergunta se deve executar o instalador quando você o abre.

A edição de arte é aplicada ao reabrir. Para distribuir a edição como nova versão, substitua a arte em `app/assets`, incremente a versão e gere um novo instalador. Configurações e gravações pessoais ficam fora da pasta de instalação.
