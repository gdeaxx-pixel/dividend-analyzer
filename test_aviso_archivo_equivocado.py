"""El paso 2 reconoce el archivo del paso 1 y lo dice (C6 del piloto, 13-nov).

Pasó de verdad: Daniel subió su historial de transacciones en el cargador de posiciones y la
app respondió «No reconocimos este archivo como el CSV de posiciones de Schwab». El rechazo
era correcto, pero el aviso no decía lo único que importaba —que ese archivo es el del paso
1— y mandó a buscar el fallo donde no estaba.
"""
import pytest

from ui.carga import _parece_historial

HISTORIAL = (b"Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount\n"
             b'"11/13/2026","Buy","MSTY","YIELDMAX","10","$11.50","","-$115.00"\n')
POSICIONES = (b'"Positions for account Individual ...as of 09:13 AM ET, 2026/11/13"\n\n'
              b'"Symbol","Description","Qty (Quantity)","Price","Mkt Val (Market Value)",'
              b'"Cost Basis","Asset Type"\n"MSTY","YIELDMAX","11.7241","$11.07","$129.83",'
              b'"$843.91","ETFs & Closed End Funds"\n')


def test_reconoce_el_historial_de_transacciones():
    assert _parece_historial(HISTORIAL)


def test_no_confunde_el_archivo_de_posiciones_con_el_historial():
    """El de posiciones trae `Qty`, no `Quantity`: si esto fallara, el camino bueno quedaría
    bloqueado con un aviso que manda al paso 1 — peor que el genérico de antes."""
    assert not _parece_historial(POSICIONES)


@pytest.mark.parametrize("crudo", [
    b"", b"\xff\xfe\x00binario", b"cualquier,cosa,sin,relacion\n1,2,3,4\n",
    "Fecha,Acción,Símbolo,Cantidad\n".encode("utf-8"),
])
def test_ante_cualquier_otra_cosa_no_se_pronuncia(crudo):
    """Sin certeza, el aviso vuelve a ser el genérico: decirle a alguien que subió el archivo
    del paso 1 cuando no es verdad lo manda a dar vueltas."""
    assert not _parece_historial(crudo)


def test_la_cabecera_puede_no_ser_la_primera_linea():
    """Schwab antepone líneas de contexto en algunas exportaciones."""
    assert _parece_historial(b'"Transactions for account ..."\n\n' + HISTORIAL)
