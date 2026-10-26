# Scripts de infraestrutura

Execute no PowerShell, a partir da raiz do projeto:

```powershell
.\infra\start_api.ps1
.\infra\start_simulator.ps1
.\infra\start_streamlit.ps1
# ou ambos, na ordem correta
.\infra\start_stack.ps1
```

`start_streamlit.ps1` aguarda o dashboard ficar saudável e imprime o link local.
`start_simulator.ps1` inicia continuamente os quatro equipamentos (`TURB-101` a
`TURB-104`) no regime `Cruzeiro` por padrão. Os regimes disponíveis são
`Cruzeiro`, `Carga_Media` e `Carga_Alta`. Os parâmetros podem ser alterados, por
exemplo: `./infra/start_simulator.ps1 -Regime Carga_Alta -IntervalSeconds 2`.
A troca de regime com o simulador já em execução deve ser feita pelos botões do
dashboard (ou `POST /regime`), sem reiniciar o processo.

As variáveis `API_PORT`, `STREAMLIT_PORT`, `API_HOST` e `STREAMLIT_HOST` permitem
substituir as portas e host padrão. `SIMULATOR_REGIME`, `SIMULATOR_INTERVAL`,
`SIMULATOR_QUANTITY` e `SIMULATOR_SEED` configuram o simulador. Os logs e PIDs
temporários ficam nesta pasta; use `.\infra\stop_services.ps1` para encerrar os
serviços iniciados pelos scripts.
