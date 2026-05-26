from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime, timedelta
import os
import sys


def calcular_fecha_emision():
    fecha = datetime.now() - timedelta(days=2)
    return fecha.strftime("%d/%m/%Y")


def ejecutar_rpa_sunat():
    # 1. Crear carpetas para guardar comprobantes y errores
    os.makedirs("Liquidaciones_PDF", exist_ok=True)
    os.makedirs("Liquidaciones_XML", exist_ok=True)
    os.makedirs("Errores", exist_ok=True)

    # 2. Cargar el Excel
    print("Cargando datos del Excel...")
    df = pd.read_excel("/Users/bensonhilario/Documents/bot sunat/compra_frutas.xlsx", dtype={'DNI': str})

    # Blindaje contra la pérdida de ceros a la izquierda (Ej: 04321567 o 00321567)
    df['DNI'] = df['DNI'].astype(str).str.zfill(8)

    fecha_emision = calcular_fecha_emision()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm?pestana=*&agrupacion=*")

        # --- FASE 1: LOGIN HÍBRIDO Y NAVEGACIÓN ---
        print("\n" + "=" * 50)
        print("POR FAVOR, INICIA SESIÓN Y RESUELVE EL CAPTCHA.")
        input("Presiona ENTER aquí en la consola cuando veas el menú principal de SUNAT...")
        print("=" * 50 + "\n")

        print("Navegando por el menú de SUNAT...")
        page.click('#divOpcionServicio2')
        page.wait_for_timeout(500)
        page.click('#nivel1_11')
        page.wait_for_timeout(500)
        page.click('#nivel2_11_5')
        page.wait_for_timeout(500)

        page.get_by_text("Liquidación de Compra Electrónica", exact=True).first.click()
        page.wait_for_timeout(500)

        page.locator('.spanNivelDescripcion').filter(has_text="Emitir Liquidación de Compra").first.click()
        page.wait_for_timeout(3000)

        formulario = page.frame_locator("#iframeApplication")

        # --- BUCLE PRINCIPAL: PROCESAR EL EXCEL ---
        for index, fila in df.iterrows():
            try:
                # Calcular el total de la operación actual
                total_fila = float(fila['Cantidad']) * float(fila['Precio'])

                print(
                    f"\n[{index + 1}/{len(df)}] Procesando DNI {fila['DNI']} - {fila['Nombre']} (Monto Estimado: S/ {total_fila:.2f})...")

                # --- CONTROL DE RIESGOS: ALERTA DE S/ 700 ---
                if total_fila > 700:
                    print("\n¡¡ALERTA!!")
                    print(f"El precio total de esta liquidación (S/ {total_fila:.2f}) supera los 700 soles.")

                    decision = ""
                    while decision not in ['Y', 'N']:
                        decision = input(
                            "¿Deseas continuar? Pulse [Y] para continuar (emite la liquidación) o [N] para abortar: ").strip().upper()

                    if decision == 'N':
                        print(f"Operación ABORTADA por el usuario para {fila['Nombre']}. Saltando al siguiente...\n")
                        continue  # Salta el resto del try y va a la siguiente fila del Excel

                # --- FASE 2: PROVEEDOR ---
                formulario.locator('#txtDocumento').fill(str(fila['DNI']))
                formulario.locator('#btnValidarDatosVendedor').click()
                page.wait_for_timeout(2000)
                formulario.locator('#btnContinuarPaso').click()

                # --- FASE 3: DIRECCIONES Y FECHA ---
                formulario.locator('#opciones_2').check()

                formulario.locator('#selDepartamento').select_option(label='LA LIBERTAD')
                formulario.locator('#selProvincia').select_option(label='TRUJILLO')
                formulario.locator('#selDistrito').select_option(label='TRUJILLO')
                formulario.locator('#txtDireccion').fill('CORRALON DE VERDURAS')
                formulario.get_by_role("button", name="Seleccionar").click()

                formulario.locator('#txtFechaEmision').evaluate(f"(el) => el.value = '{fecha_emision}'")

                # --- FASE 4: ITEMS ---
                formulario.locator('#btnItems').click()
                formulario.locator('#open-modal-item').click()
                page.wait_for_timeout(1000)

                formulario.locator('select#txtCodigo').select_option(label=fila['Producto'])
                formulario.locator('select#selUnidadMedida').select_option(label=fila['Unidad'])
                formulario.locator('input#txtValorUnitario').fill(str(fila['Precio']))
                formulario.locator('input#txtCantidad').fill(str(fila['Cantidad']))
                formulario.locator('select#selTipoIgv').select_option(label='Exonerado')
                formulario.locator('select#selTipoAfectacionIR').select_option(label='No Gravado')

                formulario.get_by_role("button", name="Aceptar").click()
                page.wait_for_timeout(1000)
                formulario.get_by_role("button", name="Cerrar").click()

                # --- FASE 5: EMISIÓN Y DESCARGA (PRODUCCIÓN) ---
                formulario.locator('#btnPreview').click()
                page.wait_for_timeout(2000)

                print("  -> Emitiendo comprobante en SUNAT...")
                formulario.locator('#btnEmitirFactura').click()
                page.wait_for_timeout(1000)
                formulario.get_by_role("button", name="Aceptar").click()

                page.wait_for_timeout(4000)

                print("  -> Descargando archivos...")
                # Descarga de XML
                with page.expect_download() as xml_info:
                    formulario.get_by_role("button", name="Descargar XML").click()
                descarga_xml = xml_info.value
                descarga_xml.save_as(f"Liquidaciones_XML/{descarga_xml.suggested_filename}")

                # Descarga de PDF
                with page.expect_download() as pdf_info:
                    formulario.get_by_role("button", name="Descargar PDF").click()
                descarga_pdf = pdf_info.value
                descarga_pdf.save_as(f"Liquidaciones_PDF/{descarga_pdf.suggested_filename}")

                print(f"  -> ¡Comprobante {descarga_pdf.suggested_filename} emitido y guardado con éxito!")

                # Recargar el formulario en blanco para el siguiente agricultor
                page.locator('.spanNivelDescripcion').filter(has_text="Emitir Liquidación de Compra").first.click()
                page.wait_for_timeout(2500)

            except Exception as e:
                print(f"  -> ERROR procesando DNI {fila['DNI']}: revisa la carpeta Errores. Detalle: {e}")
                page.screenshot(path=f"Errores/error_DNI_{fila['DNI']}.png")
                page.locator('.spanNivelDescripcion').filter(has_text="Emitir Liquidación de Compra").first.click()
                page.wait_for_timeout(2500)
                continue

        print("\n" + "=" * 50)
        print("PROCESAMIENTO POR LOTES FINALIZADO.")
        print("=" * 50)
        browser.close()


if __name__ == "__main__":
    ejecutar_rpa_sunat()