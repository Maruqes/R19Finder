# Ficha da peça com preenchimento por IA

Estado: implementação disponível. Ver [estado e validação](implementation-status.md) para o resultado e as decisões finais.

## Objetivo

Aumentar a cobertura das pesquisas de peças raras através de uma ficha estruturada: referências, nomes alternativos, características e potenciais modelos dadores. O utilizador preenche o que sabe, escolhe o fornecedor/modelo, clica em **Fill with AI**, revê os campos preenchidos e cria a peça com **Create part**.

A IA é opcional. Campos desconhecidos podem ficar vazios. Guardar uma peça não inicia uma pesquisa de anúncios. A ficha pertence ao pedido existente (`requests`), evitando introduzir já um catálogo global de peças.

## Documentos

- [Fluxo e campos](workflow.md): experiência, informação recolhida e regras de revisão.
- [Arquitetura e contratos](architecture.md): persistência, tarefas, fornecedores e integração nas pesquisas.
- [Implementação e aceitação](implementation.md): etapas, ficheiros e testes.

## Decisões propostas para a primeira versão

1. Interface em inglês, documentação de planeamento em português.
2. Formulário progressivo numa página: dados conhecidos → preenchimento por IA → revisão → criação.
3. Aplicar sugestões automaticamente apenas a campos vazios; destacar todos os valores aplicados. Alterações a valores existentes exigem escolha explícita.
4. Separar aprovação editorial de verificação factual: aceitar uma sugestão permite guardá-la, mas não comprova compatibilidade.
5. Reutilizar Codex e Open WebUI. Modelos GPT são selecionados na ligação que os disponibilize; modelos Ollama são selecionados através do Open WebUI configurado. Mostrar sempre a ligação e o modelo reais. Integrações diretas com OpenAI API/Ollama ficam fora da primeira versão.
6. Usar uma tarefa de enriquecimento própria, sem criar um pedido final antecipadamente e sem misturar o resultado com anúncios, histórico de pesquisas ou notificações Discord.
7. Reutilizar a ficha em pesquisas manuais e agendadas através de snapshots.
8. Preservar o formulário e as fotografias perante falhas, recarregamento e resultados tardios.

## Fora do âmbito inicial

Compra/contacto automático com vendedores, crawler novo, grafo global de compatibilidades, treino de modelos, tradução da interface, configuração direta de novos fornecedores e garantia de identificação por fotografia. A verificação de fontes depende das capacidades efetivamente disponíveis no fornecedor; conhecimento do modelo sem evidência fica como hipótese.

## Resultado esperado

Uma peça pode ser pesquisada pelo nome original, por nomes noutros idiomas, por referências relacionadas e por modelos dadores, mantendo explícito o que está confirmado e o que é apenas uma pista.
