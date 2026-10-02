# Dry-run: por que importa

## Um incidente que quebrou producao

Em uma tarde de terca-feira, um engenheiro de rede recebeu a solicitacao de ajustar a mascara de sub-rede de um switch de acesso para acomodar um novo bloco de IPs vindos de uma expansao do parque. A configuracao atual usava /24 em uma interface de agregacao, e o pedido era migrar para /23 para dar folga aos novos pontos de acesso. O engenheiro abriu o YAML do laboratorio, alterou o campo `mascara` de `255.255.255.0` para `255.255.254.0`, rodou o comando de aplicacao e seguiu para outra tarefa. Dez minutos depois, o telefone tocou: os usuarios do terceiro andar estavam sem acesso a impressora de rede e ao servidor de arquivos.

O que aconteceu foi que a mudanca de mascara foi aplicada diretamente no equipamento, mas o diff nao tinha sido inspecionado. A linha removida nao era so a mascara antiga: era tambem uma regra de `no ip address` que garantia que enderecos fora do bloco nao seriam aceitos na interface. Sem essa linha, o switch comecou a responder a solicitacoes ARP de faixas que nao lhe pertenciam, causando trafego paralelo e instabilidade na tabela MAC. O cliente sentiu perda de conectividade intermitente, impossibilidade de alcancar o servidor de arquivos e lentidao em sistemas que usavam a mesma VLAN. O time de suporte precisou abrir chamado, acionar o engenheiro de plantao e, como nao havia um estado anterior documentado no laboratorio, a recuperacao dependeu de backup manual do proprio equipamento. O custo foi uma hora de indisponibilidade parcial, duas horas de trabalho de recuperacao e um registro de incidente interno por alteracao nao controlada.

Esse cenario nao e raro: ele acontece quando a aplicacao e tratada como um passo trivial, e nao como um ponto de decisao. O diff e a unica prova de que o que vai sair do YAML e, de fato, o que o time espera.

## O que o dry-run faz e o que ele nao faz

O comando de plano imprime um diff completo em formato unificado para cada equipamento. Cada bloco mostra linhas removidas e adicionadas com contexto, permitindo ver nao so o que entra, mas o que sai. Alem do diff, o plano classifica o estado de cada arquivo gerado em relacao ao ultimo estado conhecido: `sem mudanca`, `mudanca gerenciada` ou `drift manual`. Quando ha problema de schema no YAML, como campos obrigatorios faltando ou referencias quebradas entre equipamentos, o plano lista esses erros antes de gerar qualquer diff, evitando surpresas. O resultado e uma visao integral do que o YAML pediu e do que o disco guarda.

O que o dry-run nao faz e igualmente importante declarar. Ele nao escreve nada em equipamento nenhum. Nenhum arquivo de saida e criado ou alterado. Ele nao toca em rede, nao abre sessao SSH, nao envia comando CLI e nao consulta estado real de dispositivo. Ele tambem nao valida conectividade real: se o diff diz que uma regra de firewall sera removida, o comando nao confirma se essa regra esta ativa em producao ou se existe dependencia oculta. O dry-run e um diff estatico e local, nao um teste de impacto.

## Por que o padrao e dry-run e nao uma opcao

A unica forma de garantir que o diff seja lido antes de aplicar e tornar o dry-run o comportamento padrao. Quando o dry-run e uma opcao desligada por bandeira, ele pode ser esquecido por pressa, habito ou falha de comunicacao em um handoff. Se o unico comando disponvel ja e o plano, nao ha como aplicar por acidente: nao existe um comando alternativo que escreva nos equipamentos. Isso nao e limitacao, e a tese do projeto: IaC cujo passo unico e "aplicar" reproduz, em escala, o problema que ele promete resolver.

Um plano nao mostra apenas o que sera incluido. Ele mostra o que sera removido, e essa remocao e muitas vezes a parte perigosa. Em regras de firewall, linhas de acesso especifico sao facilmente substituidas por regras mais amplas. Em configuracao de roteamento, a remocao de uma rota estatica pode desviar trafego de forma invisivel ate que o primeiro alarme dispare. Ler o diff antes de permitir a escrita e o que separa uma mudanca controlada de um incidente.

## Mudanca gerenciada e drift manual

A classificacao do diff faz uma distincao que muda a resposta do time. Na `mudanca gerenciada`, o YAML foi alterado, o arquivo gerado ficou para tras, e o diff aponta exatamente o que mudou. Esse e um trabalho scheduled: alguem precisa revisar o YAML, aprovar o diff e rodar o render para atualizar o arquivo no disco. O perigo e baixo porque a origem da mudanca e o proprio laboratorio.

No `drift manual`, alguem editou o arquivo diretamente no disco depois da ultima geracao. O diff aponta a linha alterada, mas a origem e externa ao YAML. Esse nao e um trabalho scheduled, e um incidente: o time precisa entender por que o arquivo foi tocado a mao, se a edicao representa uma necessidade real que precisa ser absorvida pelo YAML ou se e apenas uma correcao pontual que sera apagada no proximo render. A resposta do time nao e agendar a aplicacao; e investigar e decidir se a mao foi legitima.

Essa distincao so e possivel porque o plano compara o disco com o ultimo estado gerado registrado no manifesto, e nao apenas com o YAML. Sem essa referencia, os dois casos seriam apenas um diff com linhas diferentes.

## O custo de um diff a mais

O dry-run custa tempo e um diff para ler. E o preco mais barato disponivel. Um diff leva minutos para ser inspecionado e segundos para ser entendido por quem escreveu o YAML. Em contraste, um incidente de indisponibilidade custa horas de trabalho, pode envolver credenciais de emergencia e deixa registro que afeta avaliacoes de maturidade. O tempo gasto na leitura do diff nao e overhead; e a etapa que valida se a proxima acao faz sentido. Em um fluxo onde o unico comando disponvel e o plano, esse custo nao e uma opcao: e o trabalho.
