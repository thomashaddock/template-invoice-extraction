from typing import Any

import pandas as pd
import streamlit as st


def _fmt(value: Any, prefix: str = "", suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{prefix}{value}{suffix}"


def _fmt_currency(amount: Any, currency: str = "USD") -> str:
    if amount is None:
        return "—"
    try:
        return f"{currency} {float(amount):,.2f}"
    except (ValueError, TypeError):
        return f"{currency} {amount}"


def render_invoice_data(invoice_data: dict[str, Any]):
    """Render extracted invoice data as a structured Streamlit display."""
    if not invoice_data:
        st.warning("No invoice data available")
        return

    currency = invoice_data.get("currency", "USD")

    st.markdown("#### Invoice Summary")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Invoice #:** {_fmt(invoice_data.get('invoice_number'))}")
        st.markdown(f"**Vendor:** {_fmt(invoice_data.get('vendor_name'))}")
        st.markdown(f"**Bill To:** {_fmt(invoice_data.get('bill_to_name'))}")
        if invoice_data.get("bill_to_address"):
            st.caption(invoice_data["bill_to_address"])
    with col2:
        st.markdown(f"**Invoice Date:** {_fmt(invoice_data.get('invoice_date'))}")
        st.markdown(f"**Due Date:** {_fmt(invoice_data.get('due_date'))}")
        st.markdown(f"**Ship Mode:** {_fmt(invoice_data.get('ship_mode'))}")
        if invoice_data.get("order_id"):
            st.markdown(f"**Order ID:** {invoice_data['order_id']}")

    if invoice_data.get("ship_to_address"):
        st.markdown(f"**Ship To:** {invoice_data['ship_to_address']}")

    line_items = invoice_data.get("line_items", [])
    if line_items:
        st.markdown("#### Line Items")
        df = pd.DataFrame(line_items)
        if "amount" in df.columns:
            df["amount"] = df["amount"].apply(lambda x: f"${x:,.2f}" if x is not None else "—")
        if "rate" in df.columns:
            df["rate"] = df["rate"].apply(lambda x: f"${x:,.2f}" if x is not None else "—")
        df.columns = [c.replace("_", " ").title() for c in df.columns]
        st.dataframe(df, use_container_width=True, hide_index=True)

    total_col1, total_col2, total_col3 = st.columns(3)
    with total_col1:
        st.metric("Subtotal", _fmt_currency(invoice_data.get("subtotal"), currency))
    with total_col2:
        shipping = invoice_data.get("shipping_cost")
        tax = invoice_data.get("tax_amount")
        extras = []
        if shipping is not None:
            extras.append(f"Shipping: {_fmt_currency(shipping, currency)}")
        if tax is not None:
            extras.append(f"Tax: {_fmt_currency(tax, currency)}")
        discount = invoice_data.get("discount_amount")
        if discount is not None:
            pct = invoice_data.get("discount_percent")
            label = f"Discount ({pct}%)" if pct else "Discount"
            extras.append(f"{label}: -{_fmt_currency(discount, currency)}")
        st.metric("Adjustments", "\n".join(extras) if extras else "—")
    with total_col3:
        st.metric("Total", _fmt_currency(invoice_data.get("total_amount"), currency))
