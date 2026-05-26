import mysql.connector
import pandas as pd
import pulp


db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '949212489',
    'database': 'credit_card_fraud'
}

conn = mysql.connector.connect(**db_config)

query = "SELECT id, amount, class FROM transacciones_fraude;"
df = pd.read_sql(query, conn)

conn.close()


df['valor_esperado'] = df['amount'] * df['class']

df['tiempo_revision_min'] = 15 


capacidad_tiempo_total = 240 


prob = pulp.LpProblem("Optimizacion_Revision_Fraudes", pulp.LpMaximize)

tx_indices = df['id'].tolist()

x = pulp.LpVariable.dicts("Revisar_TX", tx_indices, cat='Binary')

prob += pulp.lpSum(df.loc[df['id'] == t, 'valor_esperado'].values[0] * x[t] for t in tx_indices), "Maximizar_Fraude_Capturado"

prob += pulp.lpSum(df.loc[df['id'] == t, 'tiempo_revision_min'].values[0] * x[t] for t in tx_indices) <= capacidad_tiempo_total, "Restriccion_Tiempo"


status = prob.solve(pulp.PULP_CBC_CMD(msg=False))


df['Asignar_A_Revision'] = df['id'].apply(lambda t: int(x[t].varValue))

plan_trabajo = df[df['Asignar_A_Revision'] == 1]

monto_total_riesgo = df['valor_esperado'].sum()
monto_recuperado = plan_trabajo['valor_esperado'].sum()
tiempo_utilizado = plan_trabajo['tiempo_revision_min'].sum()

print(f"Estado del Solucionador MILP: {pulp.LpStatus[status]}")
print("\n" + "="*65)
print("     HOJA DE RUTA PRESCRIPTIVA: AUDITORÍA DE TRANSACCIONES     ")
print("="*65)
print(f"⏱Tiempo asignado al equipo: {tiempo_utilizado} min / {capacidad_tiempo_total} min max.")
print(f"Exposición financiera total en lote: ${monto_total_riesgo:,.2f}")
print(f"Monto total óptimamente salvaguardado: ${monto_recuperado:,.2f} ({ (monto_recuperado/monto_total_riesgo)*100 :.1f}%)")
print("-"*65)
print(" LISTA DE TRANSACCIONES PRIORITARIAS PARA COLA DE REVISIÓN:")
print(plan_trabajo[['id', 'amount', 'class', 'valor_esperado']])