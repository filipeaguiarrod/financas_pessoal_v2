from datetime import datetime
import streamlit as st
import plotly.express as px
from dateutil.relativedelta import relativedelta
from .classifier import primary_classifier, secondary_classifier
from .banks import transform_xp, classify_xp,display_xp
import pandas as pd
import numpy as np

def analyze_parcelas(xp_raw,xp_class):

    """
    Input: xp_raw (df), cols = ['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela']
    Output: xp_parcelas (df), cols = ['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela', 'realizado', 'total', 'faltam'], valor-> type object(.)
    
    """
    xp_class['Valor'] = xp_class['Valor'].astype('float64')

    # De coluna Parcela calcula realizado, total e faltam.
    xp_raw[['realizado','total']] = xp_raw['Parcela'].str.split(' de ',n=2,expand=True)
    xp_parcelas = xp_raw.loc[(xp_raw['realizado']!='-')&(xp_raw['realizado']!='')].copy()
    xp_parcelas[['realizado','total']] = xp_parcelas[['realizado','total']].astype('int64')
    xp_parcelas['faltam'] = xp_parcelas['total'] - xp_parcelas['realizado']
    xp_parcelas['faltam'] = xp_parcelas['faltam'] + 1  # Corrige por exemplo 2/2 agora é minha ultima parcela mas ainda não paguei portanto falta 1  

    # Processo para converter coluna Valor para float64
    xp_parcelas['Valor'] = xp_parcelas['Valor'].str.strip()
    xp_parcelas['Valor'] = xp_parcelas['Valor'].str.replace(',','.')
    xp_parcelas['Valor'] = xp_parcelas['Valor'].str.replace('R\$', '', regex=True)
    xp_parcelas['Valor'] = xp_parcelas['Valor'].astype('float64')

    print(xp_class.info())
    print(xp_parcelas.info())

    # Classifica transações 
    xp_parcelas = xp_parcelas.merge(xp_class[['Estabelecimento','categoria','Valor']],on=['Estabelecimento','Valor'],how='left')

    return xp_parcelas

def create_cols(xp_parcelas):

    """
    Creates time cols according with xp_parcelas from analyze parcelas
    Input: xp_parcelas (df), cols = ['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela', 'realizado', 'total', 'faltam']
    Output: 
    """

    # Cria coluna com nomes de acordo com máximo tempo de parcela
    col_creating = [str(i) for i in range(1, xp_parcelas['faltam'].max()+1)]
    xp_parcelas[col_creating] = None

    for index, row in xp_parcelas.iterrows():
        to_fill = [str(i) for i in range(1,row['faltam']+1)]
        xp_parcelas.loc[xp_parcelas.index==index,to_fill] = row['Valor']

    # Creating columns, populating them and replacing with dates
    col_dates = [] 
    for i in range(0,len(col_creating)):

        date = datetime.now() + relativedelta(months=i) # According with prospect
        format_date = date.strftime("%m/%y")
        col_dates.append(format_date)

    dict_cols = {}

    for key,value in zip(col_creating, col_dates):
        dict_cols[key]=value

    xp_parcelas.rename(columns=dict_cols,inplace=True)

    xp_report = xp_parcelas[['categoria','Estabelecimento'] + col_dates]
    xp_report[col_dates] = xp_report[col_dates].astype('float64').round(2)
    xp_report.groupby(['Estabelecimento','categoria']).sum()
   

    # Create a new row 'Total' and column 'Total'
    xp_report['Total'] = xp_report.sum(axis=1)
    xp_report.sort_values(['categoria','Total'],inplace=True)
    #xp_report.loc['Total'] = xp_report.sum()

    #xp_report.reset_index(inplace=True)

    return  xp_report

def plot_cohort(xp_report):

    """ 
    Rebece xp_report(df) -> ['categoria', 'Estabelecimento',mes1,mes2,..., 'Total'], mes1,mes2...,Total float64
    """

    xp_report['categoria'] = xp_report['categoria'].str.lower()
    xp_report = xp_report.groupby('categoria').sum()

    # Sort values by the sum of each row and display from most filled to least filled
    sorted_data = xp_report.replace(0, np.nan).count(axis=1).sort_values(ascending=False).index
    xp_report_sorted = xp_report.reindex(sorted_data)

    # Create a custom colormap from white to dark blue
    custom_cmap = ['white', 'darkgray']

    # Increase the size of the plot
    fig = px.imshow(xp_report_sorted.replace(0,np.nan),
                    labels=dict(color=""),
                    color_continuous_scale=custom_cmap,
                    height=600, width=800,
                    text_auto=True)

    # Hide the color scale
    fig.update_layout(coloraxis_showscale=False)
    # Hide the grid lines
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)

    return fig

def plot_parcelas(xp_report):
    """ 
    Rebece xp_report(df) -> ['categoria', 'Estabelecimento',mes1,mes2,..., 'Total'], mes1,mes2...,Total float64
    """

    df = xp_report.copy()
    df['categoria'] = df['categoria'].str.lower()
    df = df.sort_values('Total')

    fig2 = px.bar(df,y='categoria',x='Total')
    fig2.update_layout(yaxis={'categoryorder':'total ascending'}) # add only this line

    return fig2


def execute_analysis(xp_raw,xp_class):

    """ Perform entire pipeline """

    xp_report = create_cols(analyze_parcelas(xp_raw,xp_class))
    fig = plot_cohort(xp_report)
    fig2 = plot_parcelas(xp_report)

    return xp_report, fig, fig2
