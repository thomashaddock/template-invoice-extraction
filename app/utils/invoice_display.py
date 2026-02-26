from typing import Any

import pandas as pd
import streamlit as st


def render_invoice_data(invoice_data: dict[str, Any]):
    """Render extracted invoice data as a structured Streamlit display."""
    if not invoice_data:
        st.warning("No invoice data available")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Invoice #:** {invoice_data.get('invoice_number', 'N/A')}")
        st.markdown(f"**Vendor:** {invoice_data.get('vendor_name', 'N/A')}")
        st.markdown(f"**Bill To:** {invoice_data.get('bill_to_name', 'N/A')}")
        st.markdown(f"**Order ID:** {invoice_data.get('order_id', 'N/A')}")
    with col2:
        st.markdown(f"**Invoice Date:** {invoice_data.get('invoice_date', 'N/A')}")
        st.markdown(f"**Due Date:** {invoice_data.get('due_date', 'N/A')}")
        st.markdown(f"**Ship Mode:** {invoice_data.get('ship_mode', 'N/A')}")
        currency = invoice_data.get("currency", "USD")
        total = invoice_data.get("total_amount", "N/A")
        st.markdown(f"**Total:** {currency} {total}")

    line_items = invoice_data.get("line_items", [])
    if line_items:
        st.markdown("**Line Items:**")
        df = pd.DataFrame(line_items)
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Financial Details", expanded=False):
        fin_col1, fin_col2 = st.columns(2)
        with fin_col1:
            st.markdown(f"**Subtotal:** {invoice_data.get('subtotal', 'N/A')}")
            st.markdown(f"**Discount:** {invoice_data.get('discount_percent', 0)}% (${invoice_data.get('discount_amount', 0)})")
        with fin_col2:
            st.markdown(f"**Shipping:** ${invoice_data.get('shipping_cost', 'N/A')}")
            st.markdown(f"**Tax:** ${invoice_data.get('tax_amount', 'N/A')}")
