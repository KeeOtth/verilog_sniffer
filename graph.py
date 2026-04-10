# ============================================
# ANÁLISE DE SMELLS EM CÓDIGO SYSTEMVERILOG
# Versão Python SIMPLIFICADA - Sem problemas de GTK
# ============================================

import pandas as pd
import numpy as np
import matplotlib
# Usar backend 'Agg' para evitar problemas com GTK
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# Configurar estilo
plt.style.use('default')
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 11

# ============================================
# 1. CARREGAR E PREPARAR OS DADOS
# ============================================

def carregar_dados():
    """Carrega e prepara os dados do CSV"""
    df = pd.read_csv('resultados_detalhados2.csv')
    
    # Mapear códigos para nomes em português
    smell_mapping = {
        '#1_Ambiguous_literals': 'Literais Ambíguos',
        '#2_Order_dependancy': 'Dependência de ordem',
        '#3_Identical_names': 'Nomes idênticos',
        '#4_Standard_base_literals': 'Literais sem base padrão',
        '#5_Concat_arrayLiterals': 'Literais de concatenação/array',
        '#6_Implicit_nettype': 'Nettype implícito',
        '#7_Non_automatic_init': 'Ausência de init automático'
    }
    
    df['smell_desc'] = df['smell'].map(smell_mapping)
    df['repo_curto'] = df['repo'].apply(lambda x: '/'.join(x.split('/')[:2]) if '/' in x else x)
    
    return df

def analise_estatistica(df):
    """Realiza análise estatística básica"""
    print("=" * 70)
    print("ANÁLISE DE SMELLS EM SYSTEMVERILOG")
    print("=" * 70)
    print()
    
    total_registros = len(df)
    total_repos = df['repo_curto'].nunique()
    total_arquivos = df['arquivo'].nunique()
    total_smells = df['quantidade'].sum()
    
    print("📊 ESTATÍSTICAS GERAIS:")
    print(f"Total de registros: {total_registros:,}")
    print(f"Total de repositórios: {total_repos}")
    print(f"Total de arquivos únicos: {total_arquivos}")
    print(f"Total de smells identificados: {total_smells:,}")
    print(f"Média de smells por arquivo: {df['quantidade'].mean():.2f}")
    print()
    
    return total_smells, total_repos

# ============================================
# 2. FUNÇÕES PARA GRÁFICOS
# ============================================

def criar_grafico1_distribuicao(df, total_smells):
    """Gráfico 1: Distribuição por tipo de smell"""
    sumario = df.groupby('smell_desc')['quantidade'].sum().reset_index()
    sumario = sumario.sort_values('quantidade', ascending=True)
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Cores simples
    cores = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']
    
    bars = ax.barh(sumario['smell_desc'], sumario['quantidade'], color=cores[:len(sumario)])
    
    # Adicionar valores
    for bar in bars:
        width = bar.get_width()
        ax.text(width + total_smells*0.005, bar.get_y() + bar.get_height()/2,
                f'{int(width):,}',
                va='center', ha='left', fontweight='bold')
    
    ax.set_xlabel('Número de Ocorrências')
    ax.set_title('Distribuição de Smells por Tipo', fontsize=16, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('grafico1_distribuicao.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("✅ Gráfico 1 salvo: grafico1_distribuicao.png")

def criar_grafico2_top_projetos(df, total_repos):
    """Gráfico 2: Top projetos com mais smells"""
    projetos = df.groupby('repo_curto')['quantidade'].sum().reset_index()
    projetos = projetos.sort_values('quantidade', ascending=False).head(15)
    projetos = projetos.sort_values('quantidade', ascending=True)
    
    # Truncar nomes longos
    projetos['label'] = projetos['repo_curto'].apply(
        lambda x: x[:30] + '...' if len(x) > 30 else x
    )
    
    fig, ax = plt.subplots(figsize=(14, 10))
    
    bars = ax.barh(projetos['label'], projetos['quantidade'], color='#3498db')
    
    # Adicionar valores
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 5, bar.get_y() + bar.get_height()/2,
                f'{int(width)}', va='center', ha='left', fontweight='bold')
    
    ax.set_xlabel('Total de Smells')
    ax.set_title(f'Top 15 Projetos com Mais Smells\n(Total analisado: {total_repos} repositórios)', 
                 fontsize=16, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('grafico2_top_projetos.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("✅ Gráfico 2 salvo: grafico2_top_projetos.png")

def criar_grafico3_proporcao(df, total_smells):
    """Gráfico 3: Proporção de smells"""
    sumario = df.groupby('smell_desc')['quantidade'].sum().reset_index()
    sumario['percentual'] = (sumario['quantidade'] / total_smells * 100).round(1)
    sumario = sumario.sort_values('quantidade', ascending=False)
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    # Gráfico de pizza
    cores = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']
    wedges, texts, autotexts = ax1.pie(
        sumario['quantidade'],
        labels=sumario['smell_desc'],
        colors=cores[:len(sumario)],
        autopct='%1.1f%%',
        startangle=90
    )
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    ax1.set_title('Proporção de Smells', fontsize=14, fontweight='bold')
    
    # Gráfico de barras
    sumario_bar = sumario.sort_values('percentual', ascending=True)
    y_pos = np.arange(len(sumario_bar))
    
    bars = ax2.barh(y_pos, sumario_bar['percentual'], 
                   color=cores[:len(sumario_bar)])
    
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(sumario_bar['smell_desc'])
    ax2.set_xlabel('Percentual (%)')
    ax2.set_title('Percentual por Tipo', fontsize=14, fontweight='bold')
    ax2.grid(axis='x', alpha=0.3)
    
    # Adicionar valores nas barras
    for i, (bar, perc) in enumerate(zip(bars, sumario_bar['percentual'])):
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'{perc}%', va='center', ha='left', fontweight='bold')
    
    plt.suptitle('Análise de Proporção de Smells', fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig('grafico3_proporcao.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("✅ Gráfico 3 salvo: grafico3_proporcao.png")

def criar_grafico4_cumulativo(df, total_smells):
    """Gráfico 4: Distribuição cumulativa"""
    sumario = df.groupby('smell_desc')['quantidade'].sum().reset_index()
    sumario = sumario.sort_values('quantidade', ascending=False)
    sumario['cumulativo'] = sumario['quantidade'].cumsum()
    sumario['percent_cum'] = (sumario['cumulativo'] / total_smells * 100).round(1)
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    x = range(len(sumario))
    ax.plot(x, sumario['percent_cum'], 'o-', linewidth=3, markersize=10, 
            color='#2E86AB', markerfacecolor='white', markeredgewidth=2)
    
    # Preencher área
    ax.fill_between(x, 0, sumario['percent_cum'], alpha=0.2, color='#2E86AB')
    
    # Adicionar valores
    for i, row in sumario.iterrows():
        ax.annotate(f"{row['percent_cum']}%", 
                   xy=(i, row['percent_cum']),
                   xytext=(0, 10),
                   textcoords='offset points',
                   ha='center', va='bottom',
                   fontweight='bold')
    
    ax.set_xticks(x)
    ax.set_xticklabels([desc[:15] + '...' if len(desc) > 15 else desc 
                       for desc in sumario['smell_desc']], 
                      rotation=45, ha='right')
    ax.set_ylabel('Percentual Acumulado (%)')
    ax.set_xlabel('Tipo de Smell (ordenado por frequência)')
    ax.set_title('Distribuição Cumulativa de Smells', fontsize=16, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 105)
    
    plt.tight_layout()
    plt.savefig('grafico4_cumulativo.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("✅ Gráfico 4 salvo: grafico4_cumulativo.png")

def criar_grafico5_boxplot(df):
    """Gráfico 5: Boxplot por tipo de smell"""
    ordem_smells = [
        'Nomes idênticos',
        'Literais de concatenação/array', 
        'Literais Ambíguos',
        'Literais sem base padrão',
        'Nettype implícito',
        'Ausência de init automático',
        'Dependência de ordem'
    ]
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Preparar dados
    box_data = []
    labels = []
    for smell in ordem_smells:
        subset = df[df['smell_desc'] == smell]['quantidade']
        if len(subset) > 0:
            box_data.append(subset.values)
            labels.append(smell)
    
    # Criar boxplot
    bp = ax.boxplot(box_data, labels=labels, patch_artist=True)
    
    # Colorir as caixas
    cores = ['#FFEAA7', '#DDA0DD', '#98D8C8', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
    for patch, color in zip(bp['boxes'], cores[:len(labels)]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    
    ax.set_ylabel('Quantidade por Arquivo')
    ax.set_xlabel('Tipo de Smell')
    ax.set_title('Distribuição de Quantidade por Tipo de Smell', fontsize=16, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig('grafico5_boxplot.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("✅ Gráfico 5 salvo: grafico5_boxplot.png")

def criar_grafico6_simples(df):
    """Gráfico 6: Gráfico simples de comparação"""
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    
    # 1. Total por smell
    ax1 = axes[0, 0]
    sumario = df.groupby('smell_desc')['quantidade'].sum().sort_values()
    sumario.plot(kind='barh', ax=ax1, color='skyblue')
    ax1.set_title('Total por Tipo de Smell', fontweight='bold')
    ax1.set_xlabel('Quantidade')
    
    # 2. Média por smell
    ax2 = axes[0, 1]
    media = df.groupby('smell_desc')['quantidade'].mean().sort_values()
    media.plot(kind='bar', ax=ax2, color='lightgreen')
    ax2.set_title('Média por Tipo de Smell', fontweight='bold')
    ax2.set_ylabel('Média')
    ax2.tick_params(axis='x', rotation=45)
    
    # 3. Projetos com mais smells (top 10)
    ax3 = axes[1, 0]
    projetos = df.groupby('repo_curto')['quantidade'].sum().nlargest(10).sort_values()
    projetos.plot(kind='barh', ax=ax3, color='salmon')
    ax3.set_title('Top 10 Projetos com Mais Smells', fontweight='bold')
    ax3.set_xlabel('Total de Smells')
    
    # 4. Distribuição de valores
    ax4 = axes[1, 1]
    ax4.hist(df['quantidade'], bins=30, color='purple', alpha=0.7)
    ax4.set_title('Distribuição de Valores de Smells', fontweight='bold')
    ax4.set_xlabel('Quantidade por Registro')
    ax4.set_ylabel('Frequência')
    
    plt.suptitle('Análise Completa de Smells', fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig('grafico6_analise_completa.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("✅ Gráfico 6 salvo: grafico6_analise_completa.png")

# ============================================
# 3. FUNÇÃO PRINCIPAL
# ============================================

def main():
    print("Iniciando análise de smells...")
    print("-" * 50)
    
    try:
        # 1. Carregar dados
        df = carregar_dados()
        print(f"✅ Dados carregados: {len(df):,} registros")
        
        # 2. Análise estatística
        total_smells, total_repos = analise_estatistica(df)
        
        # 3. Criar gráficos
        print("\n" + "=" * 50)
        print("CRIANDO GRÁFICOS...")
        print("=" * 50)
        
        criar_grafico1_distribuicao(df, total_smells)
        criar_grafico2_top_projetos(df, total_repos)
        criar_grafico3_proporcao(df, total_smells)
        criar_grafico4_cumulativo(df, total_smells)
        criar_grafico5_boxplot(df)
        criar_grafico6_simples(df)
        
        # 4. Salvar dados sumarizados
        sumario_smells = df.groupby('smell_desc').agg(
            total=('quantidade', 'sum'),
            media=('quantidade', 'mean'),
            projetos=('repo_curto', 'nunique'),
            arquivos=('arquivo', 'nunique')
        ).reset_index()
        
        sumario_smells['percentual'] = (sumario_smells['total'] / total_smells * 100).round(2)
        sumario_smells = sumario_smells.sort_values('total', ascending=False)
        
        sumario_smells.to_csv('sumario_smells.csv', index=False, encoding='utf-8-sig')
        print("\n✅ Dados sumarizados salvos: sumario_smells.csv")
        
        # 5. Exibir resumo
        print("\n" + "=" * 70)
        print("📋 RESUMO FINAL")
        print("=" * 70)
        
        print(f"\n📊 SMELL MAIS COMUM: {sumario_smells.iloc[0]['smell_desc']}")
        print(f"   • Ocorrências: {sumario_smells.iloc[0]['total']:,}")
        print(f"   • Percentual: {sumario_smells.iloc[0]['percentual']:.1f}%")
        print(f"   • Projetos afetados: {sumario_smells.iloc[0]['projetos']}")
        
        print(f"\n🏆 PROJETO COM MAIS SMELLS:")
        projetos = df.groupby('repo_curto')['quantidade'].sum().nlargest(1)
        for projeto, total in projetos.items():
            print(f"   • {projeto}: {total:,} smells")
        
        print(f"\n📈 ESTATÍSTICAS ADICIONAIS:")
        print(f"   • Média geral: {df['quantidade'].mean():.2f}")
        print(f"   • Mediana: {df['quantidade'].median():.2f}")
        print(f"   • Desvio padrão: {df['quantidade'].std():.2f}")
        
        print("\n" + "=" * 70)
        print("✅ ANÁLISE CONCLUÍDA COM SUCESSO!")
        print("=" * 70)
        print("\n📁 GRÁFICOS GERADOS:")
        print("1. grafico1_distribuicao.png")
        print("2. grafico2_top_projetos.png")
        print("3. grafico3_proporcao.png")
        print("4. grafico4_cumulativo.png")
        print("5. grafico5_boxplot.png")
        print("6. grafico6_analise_completa.png")
        
    except FileNotFoundError:
        print("❌ ERRO: Arquivo 'resultados_detalhados2.csv' não encontrado!")
        print("Certifique-se de que o arquivo está na mesma pasta do script.")
    except Exception as e:
        print(f"❌ ERRO durante a execução: {str(e)}")

# ============================================
# 4. EXECUTAR ANÁLISE
# ============================================

if __name__ == "__main__":
    # Instruções de instalação
    print("=" * 70)
    print("ANALISADOR DE SMELLS - SYSTEMVERILOG")
    print("=" * 70)
    print("\n📦 DEPENDÊNCIAS NECESSÁRIAS:")
    print("pip install pandas numpy matplotlib")
    print("\n📁 CERTIFIQUE-SE DE TER O ARQUIVO:")
    print("• resultados_detalhados2.csv (na mesma pasta)")
    print("\n" + "=" * 70)
    
    # Perguntar se quer continuar
    resposta = input("\nDeseja continuar? (s/n): ").strip().lower()
    
    if resposta == 's':
        main()
    else:
        print("Análise cancelada.")