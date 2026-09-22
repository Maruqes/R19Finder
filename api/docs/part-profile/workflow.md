# Fluxo e campos

## 1. Preencher o que se sabe

Página `New part`, mantendo as rotas atuais de pedidos. Texto de apoio: **Add what you know. AI can help fill in the gaps.**

Mostrar inicialmente:

- **Vehicle**: perfil existente ou descrição manual. Dados do perfil são contexto de leitura; esta operação nunca altera o carro.
- **Part description**: descrição atual, mantendo a validação de 10–5000 caracteres para criação. Pode incluir o nome, sintomas ou função.
- **Known references**: lista opcional, com código, tipo e fabricante quando conhecidos.
- **Photos**: até seis fotografias com os limites atuais; permitir identificar uma imagem como inscrição, peça completa, encaixe ou medida.
- **Quantity needed**: inteiro positivo opcional, distinto do número de referência. Campo separado **Buying unit**: individual, pair, set, unknown. Não inferir quantidade nem preferências comerciais com IA.

Secções expansíveis: **Identification**, **Technical details**, **Other compatible vehicles**, **Acceptable alternatives**, **Sources and notes**. Usar listas repetíveis para referências, compatibilidades e medidas; evitar um formulário gigante sempre aberto.

## 2. Campos da ficha

| Grupo | Campos | Regras |
| --- | --- | --- |
| Identidade | Nome curto, função, categoria, nomes alternativos com idioma | Termos alternativos podem ampliar pesquisas; não traduzir códigos OEM. |
| Referências | Código, OEM/fabricante/aftermarket/desconhecido, fabricante, relação com a peça | Distinguir referência exata, substituta, equivalente e possível correspondência. Preservar zeros, espaços e grafia original. |
| Variante | Lado, posição, fase, carroçaria, motor/versão aplicável | Não deduzir esquerda/direita apenas de uma fotografia ambígua. |
| Características | Medidas com unidade e eixo, material, acabamento, fixações, conectores/pinos, notas | Não inventar dimensões ou especificações a partir da aparência. Campos não aplicáveis ficam vazios. |
| Modelos dadores | Marca, modelo, geração, anos inicial/final, motor, restrições | Relação: mesma peça, equivalente direto, adaptação necessária ou desconhecida. Evidência por entrada. |
| Compra | Quantidade, unidade/par/conjunto, acessórios necessários | Preenchimento humano; quantidade não significa quantidade de anúncios pretendidos. |
| Alternativas | Original, aftermarket, reprodução, usada, recondicionada; aceitar adaptação ou conjunto maior | Decisões humanas opcionais. Não assumir que o utilizador aceita uma alternativa. |
| Evidências | URL, título, excerto breve ou nota, fotografia associada | Distinguir URL citada de página efetivamente consultada. |

Orçamento, localização e portes continuam nas preferências de pesquisa existentes; não duplicá-los nesta ficha.

## 3. Fill with AI

Painel compacto com **AI connection**, **Model** e, quando suportado, esforço de raciocínio. Reutilizar catálogo e configuração existentes. Não selecionar silenciosamente outra ligação se a escolhida falhar.

Mostrar resumo do que será enviado: descrição, ficha parcial, especificações do carro e fotografias selecionadas. Explicar que a operação pode consumir créditos. O clique autoriza esta chamada; não pedir uma segunda confirmação.

Para iniciar, exigir uma descrição minimamente identificável (proposta: os mesmos 10 caracteres), ligação válida e modelo selecionado. Não exigir referência, fotografia nem carro. Se faltar contexto para identificar a peça, a IA deve devolver perguntas e lacunas, não completar com invenções.

Estados: **Preparing**, **Queued**, **Filling with AI…**, **Review suggestions**, **Failed**, **Cancelled**. Desativar cliques duplicados; permitir continuar a editar e **Cancel AI fill**. Cancelar impede aplicação de resultados; informar caso a execução remota não possa ser interrompida.

## 4. Aplicar e rever

Quando chega uma resposta válida:

- Preencher campos vazios e acrescentar entradas novas às listas, com distintivo **AI suggestion**.
- Abrir as secções alteradas e mostrar contagem/resumo, sem deslocar o foco inesperadamente.
- Para campos já preenchidos, apresentar valor atual e alternativa com **Keep mine** / **Use suggestion**. O valor atual permanece por omissão.
- Usar comparação entre snapshot enviado e valor atual: nunca substituir uma edição feita enquanto a IA trabalhava, mesmo que o campo estivesse inicialmente vazio.
- Em cada proposta: **Accept**, **Edit**, **Dismiss** e, quando apropriado, **Keep as unverified**. Permitir **Accept all non-conflicting suggestions**, mantendo separadas hipóteses técnicas.
- Disponibilizar **Undo AI fill**, restaurando apenas as alterações dessa execução que não foram entretanto editadas.
- Mostrar perguntas pendentes em **Missing information**. O utilizador pode responder e executar novo preenchimento explicitamente, sem ciclo automático de chamadas.

Distinguir dois eixos:

1. Revisão: pendente, aceite, editada ou rejeitada.
2. Verificação factual: não verificada, sustentada por fonte ou confirmada pelo utilizador.

Uma referência ou compatibilidade aceite continua não verificada se não houver confirmação adicional. Não apresentar percentagens de confiança como prova. Evidência contraditória deve aparecer como conflito.

## 5. Criar a peça

Se houver sugestões pendentes, apresentar revisão com ações para aceitar, rejeitar ou guardar como hipótese. Não obrigar o utilizador a confirmar como verdade aquilo que desconhece.

Botão **Create part** guarda apenas a ficha revista, fotografias e proveniência relevante, numa transação. Após sucesso, redirecionar para o detalhe, com **Search for this part**. Sem chamada automática de pesquisa, agendamento ou Discord.

Sem uso de IA, o utilizador pode criar a peça diretamente com os requisitos atuais. Sem JavaScript, manter criação/edição manual; enriquecimento assíncrono pode exigir JavaScript e deve indicá-lo claramente.

## 6. Recuperação e edição

- Guardar rascunho no servidor ao iniciar a IA; apresentar **Resume draft** após recarregamento na mesma sessão.
- Reutilizar fotografias já carregadas no rascunho. Falhas de validação preservam os campos e imagens válidas.
- Em edição, usar o mesmo fluxo; nenhuma sugestão altera a peça guardada até **Save changes**.
- Alterar o carro invalida propostas dependentes do carro anterior e exige nova revisão; não eliminar silenciosamente campos humanos.
- Ao sair, indicar alterações por guardar. Rascunhos expiram segundo política documentada (proposta: sete dias desde última atividade).

## Exemplo de aceitação

O utilizador descreve um farolim traseiro esquerdo de um R19 e anexa uma imagem. A IA propõe nomes em francês e uma possível referência. Os nomes são aceites; a referência fica como hipótese, com a respetiva origem. A peça é criada. A pesquisa seguinte usa os nomes alternativos e investiga a referência, sem afirmar que um anúncio com esse código é necessariamente compatível.
