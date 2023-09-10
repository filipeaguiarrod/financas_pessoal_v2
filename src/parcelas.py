from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd



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

    total = xp_parcelas_ow.sum(axis=0).to_list()
    total[0] = 'TOTAL'

    xp_parcelas_ow.columns.to_list()

    xp_parcelas_ow = xp_parcelas_ow.append(pd.Series(total, index=xp_parcelas_ow.columns), ignore_index=True)

    xp_parcelas_ow['TOTAL'] = xp_parcelas_ow[col_dates].sum(axis=1)
    xp_parcelas_ow.fillna('-',inplace=True)

    return xp_parcelas_ow


