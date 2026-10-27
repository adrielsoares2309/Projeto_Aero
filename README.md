# AeroMotion Dynamics

Sistema demonstrável de monitoramento industrial: o simulador envia telemetria à API FastAPI; a API calcula as features temporais, executa o Random Forest treinado e o Isolation Forest; o dashboard Streamlit apresenta o histórico e controla o regime operacional.

## Componentes

- `api/`: validação Pydantic, inferência e histórico SQLite em `data/runtime/predictions.sqlite3`.
- `simulator.py`: gera telemetria sintética com estado físico contínuo e obedece a três regimes operacionais.
- `frontend/app.py`: dashboard Streamlit com Plotly, cartões de telemetria e botões de regime.
- `data/processed/modelos/`: artefatos treinados reais. O classificador selecionado é `random_forest.joblib`.

## Regimes de operação

O dashboard possui exatamente três botões mutuamente exclusivos na seção **REGIME DE OPERAÇÃO**:

| Regime | Alvo de carga | Temperatura | Vibração | Pressão | Rotação | Acústica | Corrente |
|---|---|---|---|---|---|---|---|
| `Cruzeiro` (padrão) | 0,25 | 51,9 °C | 1,81 mm/s | 3,81 bar | 2400,7 rpm | 44,0 dB | 20,05 A |
| `Carga_Media` | 0,55 | 61,9 °C | 2,50 mm/s | 4,20 bar | 3000,5 rpm | 52,0 dB | 27,98 A |
| `Carga_Alta` | 0,90 | 72,0 °C | 3,80 mm/s | 4,80 bar | 3500,6 rpm | 62,0 dB | 38,02 A |

Os alvos são as médias de leituras **normais** (`tipo_falha=0`) de cada `modo_operacao` no dataset original. A troca de regime:

- grava um comando em `data/runtime/simulator_control.json` via `POST /regime`;
- é aplicada pelo processo existente no ciclo seguinte, **sem reiniciar** o simulador e **sem perder** o estado ou o histórico;
- usa inércia física: carga (τ = 20 s), rotação (12 s), vibração (18 s), temperatura (90 s), pressão (35 s), acústica (20 s) e corrente (12 s);
- adiciona ruído de medição correlacionado (AR(1)), oscilações operacionais e drift lento;
- preserva a inércia de base durante a troca de regime; o esforço elevado não é uma falha artificial.

### Proporções de geração e perfis sintéticos

As proporções abaixo controlam o **perfil gerado** (`nominal`/`anormal`), não a classe
prevista pelo modelo. Elas ficam centralizadas em `REGIME_CONFIG`, no
`simulator.py`:

| Regime | Nominal | Anormal | Bloco | Intensidade do desvio |
|---|---:|---:|---:|---:|
| `Cruzeiro` | 95% | 5% | 20 leituras | 30% do afastamento das classes de falha |
| `Carga_Media` | 70% | 30% | 10 leituras | 60% |
| `Carga_Alta` | 40% | 60% | 5 leituras | 100% |

Cada bloco é montado com a contagem exata de leituras nominais e anormais e a
ordem é sorteada com semente determinística. Em `Carga_Alta` cada grupo de cinco
leituras contém exatamente duas nominais e três anormais; um bloco de 100
leituras contém 40/60. `Carga_Media` e `Cruzeiro` também produzem 70/30 e 95/5 em
blocos de 100. As anomalias de um bloco ficam em uma sequência contígua para que
a dinâmica temporal possa desenvolver o desvio, em vez de gerar picos isolados.

Os perfis anormais são derivados das médias de `tipo_falha` do dataset:

- **A — Sobrecarga térmica:** elevação da temperatura do mancal e queda da
  pressão de óleo, com inércia térmica e resposta gradual;
- **B — Solicitação mecânica e vibração:** aumento de vibração RMS e de emissão
  acústica;
- **C — Desvio combinado:** elevação moderada de temperatura, vibração e
  corrente elétrica.

A distribuição A/B/C é configurável por regime (por exemplo, 34%/33%/33% em
`Carga_Alta`) e é balanceada por uma fila determinística. Uma leitura anormal é
um cenário de teste; **não** é uma falha confirmada nem um rótulo de falha.

As faixas de geração são apenas o mínimo/máximo observado no dataset tratado:
temperatura 40,0–119,6 °C; vibração 0,08–15,17 mm/s; pressão 0,68–5,59 bar;
rotação 2278,2–3641,4 rpm; acústica 34,15–104,0 dB; corrente 15,35–62,54 A.
**Não são limites de segurança industrial.** Os limites operacionais usados
pelos indicadores do dashboard continuam em `SENSOR_LIMITS`; uma anomalia
sintética pode ultrapassá-los de propósito, dentro das faixas de geração.

O simulador grava heartbeat/estado em `data/runtime/simulator_state.json` e usa `data/runtime/simulator.lock` para impedir instâncias duplicadas. O regime é armazenado separadamente da classe prevista (`regime_operacional` vs. `classe_prevista`), junto de `origem_leitura` (`simulada`/`real`), `perfil_sintetico`, `perfil_anomalia`, `tipo_falha_predita` e das probabilidades do modelo. As colunas novas do SQLite são aditivas: registros históricos não são apagados.

## Executar no Windows

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\infra\start.ps1
```

Links: API/Swagger em `http://127.0.0.1:8000/docs` e dashboard em `http://127.0.0.1:8501`. Para encerrar ambos: `.\infra\start.ps1 -Stop`.

Também é possível executar em terminais separados:

```powershell
python -m uvicorn api.main:app --reload
python -m streamlit run frontend/app.py
python simulator.py --regime Cruzeiro --intervalo 5
```

Para trocar de regime, use os três botões da sidebar. Alternativamente, pela API:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/regime `
  -ContentType 'application/json' -Body '{"regime":"Carga_Alta"}'
Invoke-RestMethod http://127.0.0.1:8000/regime
```

Se o simulador estiver offline, o comando fica registrado em
`data/runtime/simulator_control.json` e é aplicado no próximo início; o cartão
de regime indica claramente o estado `Offline`.

## Endpoints

- `GET /health`: estado e artefatos carregados.
- `POST /predict`: uma leitura de sensor (com metadados opcionais de regime, origem e perfil sintético).
- `POST /predict-batch`: lista de leituras, em ordem temporal por equipamento.
- `GET /predictions?limit=100&equipamento=TURB-101`: histórico persistente.
- `GET /stats`: estatísticas das previsões, incluindo contagem por regime/origem e a avaliação por regime com leituras geradas nominais/anormais, proporções, distribuição real das classes previstas, probabilidades médias e tempo médio de inferência. `leituras` é o total do regime; `leituras_com_perfil` é o coorte com perfil sintético registrado. As chaves `classes_previstas`, `probabilidade_media_por_classe` e `tempo_medio_inferencia_ms` usam apenas esse coorte; as chaves `*_todas` preservam a visão de todo o histórico do regime.
- `GET /regime`: regime selecionado, regime ativo, última transição, tempo desde a transição e heartbeat do simulador.
- `POST /regime`: solicita `Cruzeiro`, `Carga_Media` ou `Carga_Alta` ao simulador.
- `GET /regimes`: lista os regimes disponíveis e seus rótulos.

Exemplo de leitura:

```json
{
  "timestamp": "2026-10-22T10:00:00",
  "id_equipamento": "TURB-101",
  "modo_operacao": "Carga_Media",
  "regime_operacional": "Carga_Media",
  "origem_leitura": "simulada",
  "perfil_sintetico": "anormal",
  "perfil_anomalia": "B",
  "horas_operacao_acumuladas": 4500.0,
  "temperatura_mancal_c": 62.5,
  "vibracao_rms_mms": 8.4,
  "pressao_oleo_bar": 4.2,
  "rotacao_rpm": 3000.0,
  "emissao_acustica_db": 76.0,
  "corrente_eletrica_amp": 30.0
}
```

O `tipo_falha_predita` retornado pela API é sempre o nome da classe real do
modelo. Ele é diferente de `perfil_sintetico`/`perfil_anomalia`: estes descrevem
o cenário que o simulador tentou gerar. O dashboard mostra essas duas
distribuições separadamente em **Avaliação do Modelo → Reação do Modelo por
Regime**.

## Contrato de ML e limitações

O pipeline Random Forest já contém imputação, `RobustScaler` e codificação one-hot; a API o recebe como `DataFrame` e não pré-processa os dados uma segunda vez. As médias e desvios de temperatura/vibração usam janelas temporais de 1 h e 6 h por equipamento e `severidade_dinamica` é a razão vibração/RPM. Até haver duas leituras na janela de 1 h, o dashboard sinaliza aquecimento e o imputador do pipeline lida com os desvios ainda indisponíveis.

O regime operacional **nunca** define a classe prevista. O dashboard exibe a saída real do modelo, mesmo que ela não corresponda ao regime. Nos perfis nominais dos três regimes o classificador tende a retornar `Normal` com alta confiança; quando o gerador produz um perfil anormal, o modelo pode ou não reconhecer o padrão. Essa reação é registrada sem correção. O Isolation Forest pode sinalizar algumas amostras como anomalias por conta própria; isso também é uma saída autêntica dos artefatos.

A dinâmica temporal (inércia, AR(1), oscilações, persistência dos desvios e retorno gradual) é uma **hipótese de modelagem** explícita, pois o dataset original é essencialmente independente dentro de cada regime. A persistência dos componentes de anomalia pode fazer uma leitura marcada como nominal ainda carregar resíduo térmico do episódio anterior, sobretudo em `Carga_Alta`; a proporção 40/60 é do **gerador**, não uma promessa de que toda leitura nominal estará exatamente no centro da faixa nominal. As probabilidades são saídas do classificador, não confirmação de falha. As estatísticas e leituras do simulador representam simulação (`origem_leitura="simulada"`), não desempenho operacional real nem falhas físicas confirmadas. Nenhum comando é enviado a equipamentos ou PLCs reais.

## Testes

```powershell
python -m unittest discover -s tests -v
```

São 35 testes cobrindo as proporções 95/5, 70/30 e 40/60 em blocos de 100
(com 2/5 em cada bloco de `Carga_Alta`), distribuição dos perfis A/B/C,
ausência de NaN/infinitos, compatibilidade das 17 features com o pipeline,
continuidade e faixas de geração, troca de regime, lock de instância única,
migração aditiva do SQLite, preservação do histórico, separação entre perfil
gerado e classe prevista, endpoints da API, botões da sidebar e marcadores de
transição.

## Validação ao vivo dos dados sintéticos

Em 26/10/2026 foi executada uma validação com a classe `TelemetrySimulator`
real, seed `20261026`, 100 ciclos × 4 equipamentos por regime e POSTs em
`/predict-batch` contra a API real. Foram geradas 1.200 leituras, IDs
`25948–27147`, sem impor a classe do modelo. Cada equipamento produziu
exatamente 95/5, 70/30 e 40/60; em `Carga_Alta` todos os blocos de cinco
leituras tiveram 2 nominais e 3 anormais. Todas as leituras ficaram finitas,
dentro das faixas de geração, e os saltos máximos por equipamento
permaneceram compatíveis com a dinâmica temporal.

Códigos: `0` Normal, `1` Desgaste de Rolamento, `2` Desbalanceamento do Rotor,
`3` Cavitação/Superaquecimento.

| Regime | Gerado N/A | Classes previstas (0/1/2/3) | Inferência média |
|---|---:|---|---:|
| `Cruzeiro` | 380/20 | 400/0/0/0 | 81,55 ms |
| `Carga_Media` | 280/120 | 366/16/18/0 | 80,23 ms |
| `Carga_Alta` | 160/240 | 149/167/77/7 | 80,27 ms |

Em `Carga_Alta`, o perfil B foi previsto como `Desgaste_Rolamento` em 86/86
leituras; o perfil C como `Desbalanceamento_Rotor` em 55/75 e como classe 1
em 20/75; o perfil A ficou majoritariamente `Normal` (41/79), com 22/79 em
classe 1, 9/79 em classe 2 e 7/79 em classe 3. Isso mostra reação real e
heterogênea do classificador, não uma regra derivada do perfil sintético.

Na troca de regime ao vivo, o mesmo processo de estado (`PID 6704`) atendeu
`Cruzeiro → Carga_Media → Carga_Alta → Cruzeiro`; uma segunda tentativa de
iniciar o simulador foi recusada pelo lock. O histórico anterior foi
preservado: 25.828 linhas sem perfil continuaram intactas e o total passou para
27.147 linhas. O dashboard passou a exibir a seção **Reação do Modelo por
Regime — Dados Sintéticos** e foi corrigida a leitura dos CSVs com
`utf-8-sig`, que evitava um erro de BOM na comparação de modelos.

Limitações desta validação: foi uma execução controlada, com uma seed e
timestamps monotônicos gerados em lote (o `dt` físico foi de 5 s, mas o relógio
de parede não foi esperado por 25 minutos). Em `Carga_Alta`, 108/160 leituras
nominais foram previstas como `Normal`; as outras 52 carregaram resíduo
térmico/mecânico do episódio anterior e foram classificadas como classe 1 ou 2.
Isso é persistência intencional do gerador, não uma promessa de que toda
leitura nominal será classificada como `Normal`. Os resultados não representam
desempenho em equipamentos reais e nenhum comando foi enviado a PLCs.
