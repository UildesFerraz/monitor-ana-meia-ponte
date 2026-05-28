// Configurações

// Configurações
const API_URL = "http://localhost:8000/api/dashboard";
const NIVEL_ESTIAGEM = 2.80;
const NIVEL_CHEIA = 5.00;

// Estado
let appData = null;
let currentMetric = 'nivel'; // 'nivel' ou 'vazao'

// Elementos DOM
const loadingEl = document.getElementById('loading');
const contentEl = document.getElementById('dashboard-content');
const metricSelector = document.getElementById('metric-selector');

// Iniciar aplicação
async function init() {
  try {
    const response = await fetch(`${API_URL}?dias_previsao=180`);
    if (!response.ok) throw new Error("Erro na API");
    
    appData = await response.json();
    
    // Atualizar KPIs
    document.getElementById('kpi-date').innerText = appData.atualizacao.split(' ')[0];
    document.getElementById('kpi-nivel').innerText = appData.nivel_atual.toFixed(2) + ' m';
    document.getElementById('kpi-vazao').innerText = (appData.vazao_atual * 1000).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + ' L/s';
    
    const alertas = [
        { nome: 'Atenção (12m³)', valor: 12.0, cor: '#fde047' },
        { nome: 'Alerta (9m³)', valor: 9.0, cor: '#fbbf24' },
        { nome: 'Crítico 1 (5.5m³)', valor: 5.5, cor: '#f97316' },
        { nome: 'Crítico 2 (4m³)', valor: 4.0, cor: '#ef4444' },
        { nome: 'Crítico 3 (3m³)', valor: 3.0, cor: '#b91c1c' },
        { nome: 'Crítico 4 (2m³)', valor: 2.0, cor: '#7f1d1d' }
    ];

    let htmlLista = '';

    for (let alerta of alertas) {
        if (appData.vazao_atual <= alerta.valor) {
            htmlLista += `<div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom: 1px solid rgba(255,255,255,0.05); color: ${alerta.cor}">
                            <span>${alerta.nome}</span>
                            <strong>Já atingido</strong>
                          </div>`;
        } else {
            // Vasculhar o array de projeção para encontrar quando vai bater
            let dataAtingida = null;
            let dias = null;
            
            for (let i = 0; i < appData.extrapolacao_fisica.length; i++) {
                if (appData.extrapolacao_fisica[i].vazao <= alerta.valor) {
                    dataAtingida = appData.extrapolacao_fisica[i].data;
                    dias = i + 1;
                    break;
                }
            }

            if (dataAtingida) {
                let partes = dataAtingida.split('-');
                let strData = `${partes[2]}/${partes[1]}`;
                htmlLista += `<div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom: 1px solid rgba(255,255,255,0.05); color: ${alerta.cor}">
                                <span>${alerta.nome}</span>
                                <strong>${strData} (~${dias}d)</strong>
                              </div>`;
            } else {
                htmlLista += `<div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom: 1px solid rgba(255,255,255,0.05); color: #64748b">
                                <span>${alerta.nome}</span>
                                <strong>> 180 dias</strong>
                              </div>`;
            }
        }
    }
    
    document.getElementById('kpi-estiagem-lista').innerHTML = htmlLista;

    // Listeners
    metricSelector.addEventListener('change', (e) => {
        currentMetric = e.target.value;
        renderChart();
    });

    // Renderizar e Mostrar
    loadingEl.classList.add('hidden');
    contentEl.classList.remove('hidden');
    
    renderChart();

  } catch (err) {
    console.error(err);
    loadingEl.innerHTML = `<p style="color:var(--danger-color)">❌ Erro ao carregar dados da API: Certifique-se que o backend FastAPI está rodando na porta 8000.</p>`;
  }
}

// Renderizar o Gráfico com Plotly
function renderChart() {
    if (!appData) return;

    const metricKey = currentMetric; // 'nivel' ou 'vazao'
    const metricProphetYhat = currentMetric === 'nivel' ? 'nivel_yhat' : 'vazao_yhat';
    
    const titleY = currentMetric === 'nivel' ? 'Nível (m)' : 'Vazão (L/s)';

    // Multiplicador: se for vazão, multiplicar dados da API por 1000 para converter de m³/s para L/s
    const getVal = (val) => currentMetric === 'nivel' ? val : val * 1000;

    // Histórico
    const traceHist = {
        x: appData.dados.map(d => d.data),
        y: appData.dados.map(d => getVal(d[metricKey])),
        name: 'Histórico Observado',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#38bdf8', width: 2 }
    };

    // Extrapolação Física
    const traceFisico = {
        x: appData.extrapolacao_fisica.map(d => d.data),
        y: appData.extrapolacao_fisica.map(d => getVal(d[metricKey])),
        name: 'Extrapolação Física (Recessão)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#f43f5e', width: 2, dash: 'dash' }
    };

    // Modelo Prophet
    const traceProphet = {
        x: appData.previsao_prophet.map(d => d.data),
        y: appData.previsao_prophet.map(d => getVal(d[metricProphetYhat])),
        name: 'Previsão Prophet',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#10b981', width: 2, dash: 'dot' }
    };

    const data = [traceHist, traceFisico];
    if (appData.previsao_prophet.length > 0) {
        data.push(traceProphet);
    }

    const layout = {
        title: { text: `Projeção de ${titleY}`, font: { color: '#f8fafc', size: 20 } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8' },
        xaxis: { 
            gridcolor: 'rgba(255,255,255,0.1)',
            zerolinecolor: 'rgba(255,255,255,0.1)'
        },
        yaxis: { 
            title: titleY,
            gridcolor: 'rgba(255,255,255,0.1)',
            zerolinecolor: 'rgba(255,255,255,0.1)'
        },
        margin: { t: 50, l: 50, r: 20, b: 50 },
        legend: { orientation: 'h', y: -0.2 }
    };

    // Adicionar Linhas de Alerta no Gráfico
    if (currentMetric === 'nivel') {
        layout.shapes = [
            {
                type: 'line', x0: traceHist.x[0], x1: traceFisico.x[traceFisico.x.length-1],
                y0: NIVEL_ESTIAGEM, y1: NIVEL_ESTIAGEM,
                line: { color: '#fbbf24', width: 2, dash: 'dot' }
            },
            {
                type: 'line', x0: traceHist.x[0], x1: traceFisico.x[traceFisico.x.length-1],
                y0: NIVEL_CHEIA, y1: NIVEL_CHEIA,
                line: { color: '#818cf8', width: 2, dash: 'dot' }
            }
        ];
    } else if (currentMetric === 'vazao') {
        // Tabela de criticidade (L/s direto)
        const alertasVazao = [
            { nome: 'Atenção (12000 L/s)', valor: 12000.0, cor: '#fde047' },
            { nome: 'Alerta (9000 L/s)', valor: 9000.0, cor: '#fbbf24' },
            { nome: 'Crítico 1 (5500 L/s)', valor: 5500.0, cor: '#f97316' },
            { nome: 'Crítico 2 (4000 L/s)', valor: 4000.0, cor: '#ef4444' },
            { nome: 'Crítico 3 (3000 L/s)', valor: 3000.0, cor: '#b91c1c' },
            { nome: 'Crítico 4 (2000 L/s)', valor: 2000.0, cor: '#7f1d1d' }
        ];

        alertasVazao.forEach(alerta => {
            data.push({
                x: [traceHist.x[0], traceFisico.x[traceFisico.x.length-1]],
                y: [alerta.valor, alerta.valor],
                mode: 'lines',
                name: alerta.nome,
                line: { color: alerta.cor, width: 2, dash: 'dot' },
                hoverinfo: 'none'
            });
        });
    }

    Plotly.newPlot('plotly-chart', data, layout, {responsive: true});
}

// Iniciar
window.addEventListener('DOMContentLoaded', init);
