from datetime import datetime
import streamlit as st
import plotly.express as px
from dateutil.relativedelta import relativedelta
from .classifier import primary_classifier, secondary_classifier
import pandas as pd
import numpy as np

def analyze_parcelas(xp):

    """
    Receives a xp file that will contain first analyzes 
    """

    # Make a parse into Parcela column

    #xp['Parcela'] = xp['Parcela'].astype('str')

    xp[['realizado','total']] = xp['Parcela'].str.split(' de ',n=2,expand=True)

    xp_parcelas = xp.loc[xp['realizado']!='-'].copy()
    xp_parcelas[['realizado','total']] = xp_parcelas[['realizado','total']].astype('int64')
    xp_parcelas['faltam'] = xp_parcelas['total'] - xp_parcelas['realizado']

    xp_parcelas['Valor'] = xp_parcelas['Valor'].str.strip()
    xp_parcelas['Valor'] = xp_parcelas['Valor'].str.replace(',','.')
    xp_parcelas['Valor'] = xp_parcelas['Valor'].astype('float64')

    # Corrige por exemplo 2/2 agora é minha ultima parcela mas ainda não pague! falta 1  

    xp_parcelas['faltam'] = xp_parcelas['faltam'] + 1  

    # Cria coluna com nomes de acordo com máximo tempo de parcela

    col_creating = [str(i) for i in range(1, xp_parcelas['faltam'].max()+1)]

    xp_parcelas[col_creating] = None

    for index, row in xp_parcelas.iterrows():

        #print('faltam',row['faltam'])
        to_fill = [str(i) for i in range(1,row['faltam']+1)]
        #print(to_fill)

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

    # Returning just overview of main information !

    xp_parcelas_ow = xp_parcelas[['Estabelecimento'] + col_dates]

    xp_parcelas_ow[col_dates] = xp_parcelas_ow[col_dates].astype('float64').round(2)
    xp_parcelas_ow.set_index('Estabelecimento',inplace=True)

    #xp_parcelas_ow = xp_parcelas_ow.fillna(0.00)

    # Create a new row 'Total' and column 'Total'
    xp_parcelas_ow['Total'] = xp_parcelas_ow.sum(axis=1)
    xp_parcelas_ow.loc['Total'] = xp_parcelas_ow.sum()

    '''total = xp_parcelas_ow.sum(axis=0).to_list()
    total[0] = 'TOTAL'

    xp_parcelas_ow.columns.to_list()

    xp_parcelas_ow = xp_parcelas_ow.append(pd.Series(total, index=xp_parcelas_ow.columns), ignore_index=True)

    xp_parcelas_ow['TOTAL'] = xp_parcelas_ow[col_dates].sum(axis=1).round(2)
    xp_parcelas_ow.fillna('-',inplace=True)'''

    #xp_parcelas_ow[[col_dates]] = xp_parcelas_ow[col_dates].astype('float64')

    return  xp_parcelas_ow

def plot_parcelas(df_parc_class):
    """ 
    Rebece df classificado de parcelas e plota
    gráficos
    """

    df = df_parc_class.copy()
    df['categoria'] = df['categoria'].str.lower()
    df = df.sort_values('Total')
    print(df)

    fig = px.bar(df,y='categoria',x='Total')

    fig.update_layout(yaxis={'categoryorder':'total ascending'}) # add only this line

    return fig