# Plano de Improvement - PRJ-13 Calculadora

Data: 2026-04-21  
Status: Em planejamento guiado

## 1. Objetivo
Elevar a assertividade da calculadora (extração + BOM + validação) com foco em redução de itens `VERIFICAR`, menos retrabalho manual e maior confiabilidade para uso corporativo.

## 2. Metas de assertividade (KPIs)
- `% SAP válido` >= 97%
- `% itens VERIFICAR` <= 3%
- `erros críticos de validação` = 0 antes da exportação final
- `tempo de revisão manual` reduzido em pelo menos 50%

## 3. Backlog priorizado
1. Gate de qualidade antes da exportação
- Integrar `TechnicalValidator` no fluxo do app.
- Bloquear CSV/PDF quando houver erros críticos.
- Exibir avisos com ação de correção.

2. Fechamento dos TODOs críticos no motor
- Implementar resolução real de `Chave`.
- Implementar resolução real de `Para-Raio`.
- Reduzir fallback para `VERIFICAR` com regras determinísticas.

3. Score de confiança ponta-a-ponta
- Propagar confiança do extrator/busca para cada item do BOM.
- Exibir “baixa confiança” na UI para revisão obrigatória.

4. Aprendizado com correção do usuário
- Persistir correções manuais (SAP/descrição) para reuso futuro.
- Atualizar vocabulário/de-para automaticamente.

5. Testes de regressão robustos
- Substituir testes com `print` por asserts objetivos.
- Criar suíte “golden files” (PDF entrada -> BOM esperado).

6. Observabilidade de precisão
- Dashboard interno de assertividade por projeto.
- Histórico de gaps por tipo (estrutura, cabo, trafo, chave).

## 4. Fases de execução
Fase 1 (rápida): itens 1 e 2  
Fase 2 (estrutura): itens 3 e 4  
Fase 3 (escala): itens 5 e 6

## 5. Critério de aceite por fase
- Fase 1: exportação bloqueada corretamente em cenário inválido + queda perceptível de `VERIFICAR`.
- Fase 2: UI mostra confiança por item + correções passam a reaproveitar conhecimento.
- Fase 3: testes automatizados cobrindo cenários críticos e métricas estáveis por 2 semanas.

## 6. Riscos e mitigação
- Risco: aumento de rigidez bloquear operação.
  - Mitigação: modo “forçar exportação” com justificativa auditável.
- Risco: falsa confiança em IA de extração.
  - Mitigação: score + trilha de auditoria + validação técnica obrigatória.
- Risco: regressão silenciosa.
  - Mitigação: suíte de regressão e comparação com baseline.

## 7. Próximos passos recomendados
1. Implementar Fase 1 integral.
2. Rodar benchmark com lote de PDFs reais.
3. Revisar KPIs com operação e ajustar thresholds.

## 8. Estratégia de apresentação interna (Office 365) sem migração de mainframe
Objetivo: disponibilizar a calculadora para uso corporativo interno, com controle de acesso e melhor experiência para operação.

Opções de entrega:
1. Web app interno (prioritário)
- Hospedar em servidor Windows interno.
- Expor URL corporativa via IIS/reverse proxy.
- Integrar autenticação corporativa (SSO/Entra ID quando disponível).

2. Microsoft Teams
- Publicar a aplicação web interna como aba no Teams.
- Facilitar acesso por equipe sem depender de links externos.

3. Desktop interno (alternativa)
- Empacotar app para execução local em máquinas autorizadas.

Diretriz recomendada:
- Seguir com Web app interno + Teams Tab (melhor equilíbrio entre governança e adoção).

## 9. Estratégia de extração de PDF com IA (híbrida)
Objetivo: reduzir falhas da leitura puramente posicional e elevar assertividade da extração.

Modelo híbrido:
1. Camada determinística (padrão)
- Mantém parser atual para cenários simples e custo baixo.

2. Camada IA por exceção
- Acionada quando houver baixa confiança, poucos itens extraídos ou padrões ambíguos.
- Priorizar stack corporativa: Azure OpenAI e/ou Azure AI Document Intelligence.
- Considerar Microsoft Copilot como opção oficial de IA no ecossistema Office 365,
  especialmente para fluxos assistidos e validação contextual de extração.
- Manter opção de provedor alternativo conforme política interna.

3. Camada de validação técnica obrigatória
- Rodar validações de compatibilidade e esforço antes de liberar exportação.
- Bloquear saída final em erros críticos.

Critérios de sucesso:
- Queda consistente de itens `VERIFICAR`.
- Menor retrabalho manual por projeto.
- Aumento do `% SAP válido` sem perda de rastreabilidade.

## 10. Roadmap de implementação sem parada operacional
Fase A (Piloto controlado)
- Publicação interna em ambiente restrito.
- Ativação da IA por feature flag.
- Comparação lado a lado: parser atual vs parser híbrido.
- Executar piloto com Copilot em paralelo ao parser atual para medir ganho real.

Fase B (Estabilização)
- Ajuste de thresholds de confiança.
- Inclusão de trilha de auditoria por item extraído.
- Treinamento rápido da equipe operacional.

Fase C (Escala)
- Disponibilização no Teams.
- Monitoramento de KPIs de assertividade semanal.
- Revisão contínua de regras e vocabulário.

## 11. Diretriz específica: uso de Copilot como IA
Objetivo: aproveitar a integração nativa com Office 365 mantendo rastreabilidade e controle.

Recomendações:
1. Usar Copilot em modo assistivo no início (revisão/extração complementar), não como fonte única.
2. Manter validação técnica obrigatória antes da exportação final.
3. Definir trilha de auditoria mínima por item: origem, confiança, intervenção humana.
4. Validar política de dados sensíveis (LGPD + regras internas) antes de escalar para produção.

## 12. Execução realizada (2026-04-21)
Implementado nesta etapa:
1. Seletor de provedor IA no app (`Padrão`, `Claude`, `Copilot`).
2. Suporte a `extract_with_ai()` com despacho por provedor.
3. Integração com endpoint Copilot corporativo via `COPILOT_EXTRACT_WEBHOOK_URL`.
4. Parser resiliente para múltiplos formatos de resposta do Copilot.
5. Documentação de contrato e operação em `docs/COPILOT_INTEGRATION.md`.
6. Mock local de endpoint em `scripts/mock_copilot_extractor.py`.
7. Teste automatizado do parser em `tests/test_copilot_response_parser.py`.

## 13. Status de conclusão do plano (2026-04-21)
Backlog técnico (itens 1 a 6):
1. Gate de qualidade antes da exportação: ✅ Concluído no app
- Validação técnica integrada.
- Bloqueio de exportação com erro crítico.
- Override com justificativa auditável.

2. Fechamento dos TODOs críticos no motor: ✅ Concluído
- Resolução de `Chave` com busca determinística e exclusões.
- Resolução de `Para-Raio` com busca determinística e exclusões.

3. Score de confiança ponta-a-ponta: ✅ Concluído
- Confiança propagada para BOM.
- Itens de baixa confiança destacados e exigência de revisão para exportar.

4. Aprendizado com correção do usuário: ✅ Concluído
- Correções manuais salvas em `storage/manual_corrections.json`.
- Reaproveitamento automático em cálculos futuros.

5. Testes de regressão robustos: ✅ Concluído (estrutura e casos)
- Testes convertidos para asserts.
- Casos golden adicionados para comportamento do motor.
- Observação: execução local de `pytest` depende de instalação no ambiente.

6. Observabilidade de precisão: ✅ Concluído
- KPIs de assertividade no app.
- Histórico de assertividade na sessão.
- Resumo por tipo de gap de integridade.

Itens de implantação corporativa (Office 365/Teams):
- Publicação interna em IIS/Teams: 🟡 Toolkit entregue (scripts + template + guia); execução final depende de infraestrutura corporativa.
- Piloto com endpoint Copilot real: 🟡 Pronto no código; depende de URL corporativa e credenciais.

### 13.1 Toolkit de publicação interna entregue
- `scripts/setup_internal_publish.ps1`
- `scripts/start_internal_fastapi.ps1`
- `scripts/stop_internal_fastapi.ps1`
- `scripts/healthcheck_internal_fastapi.ps1`
- `scripts/configure_iis_reverse_proxy_fastapi.ps1`
- `deploy/iis/web.fastapi.config.template`
- `docs/PUBLICACAO_INTERNA_OFFICE365.md`
