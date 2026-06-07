# Copyright (c) 2026-present NexaQL Contributors
"""Document type registry — extensible catalog of all known doc types.

Ships with comprehensive built-in types covering financial, legal,
communication, operational, personal, and reference documents.
Users can register custom types at runtime or via YAML configuration.
"""

from __future__ import annotations

from typing import Optional

from nexaql.taxonomy.models import (
    ClassificationResult,
    ContextTierDef,
    DocCategory,
    DocSubtypeDef,
    DocTypeDef,
    EntityFieldDef,
    EntityTemplate,
    LinkStrategy,
    MessageIntentDef,
)

# Module-level singleton
_default_registry: Optional[DocTypeRegistry] = None


class DocTypeRegistry:
    """Registry of document type definitions.

    Thread-safe read access. Registration should happen at startup.
    """

    def __init__(self) -> None:
        self._types: dict[str, DocTypeDef] = {}
        self._categories: dict[str, list[str]] = {}

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, doc_type: DocTypeDef) -> None:
        """Register a document type definition."""
        key = doc_type.qualified_name
        self._types[key] = doc_type
        cat = doc_type.category.value
        if cat not in self._categories:
            self._categories[cat] = []
        if key not in self._categories[cat]:
            self._categories[cat].append(key)

    def register_many(self, doc_types: list[DocTypeDef]) -> None:
        """Register multiple document types at once."""
        for dt in doc_types:
            self.register(dt)

    # ── Lookup ───────────────────────────────────────────────────────────

    def get(self, qualified_name: str) -> DocTypeDef | None:
        """Look up a doc type by qualified name (e.g. 'legal.contract')."""
        return self._types.get(qualified_name)

    def resolve(self, path: str) -> DocTypeDef | None:
        """Resolve a dotted path like 'legal.contract.msa'.

        Returns the DocTypeDef for 'legal.contract'. If 'msa' is a valid
        subtype, you can access it via the returned type's subtypes dict.
        """
        parts = path.split(".")
        if len(parts) < 2:
            return None
        qualified = f"{parts[0]}.{parts[1]}"
        return self._types.get(qualified)

    def resolve_subtype(self, path: str) -> tuple[DocTypeDef | None, str | None]:
        """Resolve a full path including subtype.

        Returns (DocTypeDef, subtype_name) or (None, None).
        """
        parts = path.split(".")
        if len(parts) < 2:
            return None, None
        qualified = f"{parts[0]}.{parts[1]}"
        doc_type = self._types.get(qualified)
        subtype = parts[2] if len(parts) > 2 else None
        return doc_type, subtype

    def list_types(self, category: str | None = None) -> list[DocTypeDef]:
        """List all registered types, optionally filtered by category."""
        if category:
            keys = self._categories.get(category, [])
            return [self._types[k] for k in keys if k in self._types]
        return list(self._types.values())

    def list_categories(self) -> list[str]:
        """List all categories that have registered types."""
        return list(self._categories.keys())

    def all_classification_hints(self) -> dict[str, list[str]]:
        """Return {qualified_name: hints} for all types + subtypes.

        Useful for building an LLM classification prompt.
        """
        result: dict[str, list[str]] = {}
        for key, dt in self._types.items():
            result[key] = list(dt.classification_hints)
            for sub_name, sub_def in dt.subtypes.items():
                result[f"{key}.{sub_name}"] = list(sub_def.classification_hints)
        return result

    @property
    def type_count(self) -> int:
        return len(self._types)

    def to_classification_prompt(self) -> str:
        """Generate an LLM system prompt for document classification.

        Returns a structured prompt listing all types, subtypes, and their
        classification hints for use with any LLM.
        """
        lines = [
            "You are a document classifier. Given a document's content (or a summary),",
            "classify it into the most specific type and subtype from the taxonomy below.",
            "",
            "Return JSON: {\"category\": \"...\", \"type\": \"...\", \"subtype\": \"...\" or null,",
            "\"confidence\": 0.0-1.0, \"reasoning\": \"...\"}",
            "",
            "## Taxonomy",
            "",
        ]

        for cat in sorted(self._categories.keys()):
            lines.append(f"### {cat.upper()}")
            for key in self._categories[cat]:
                dt = self._types[key]
                lines.append(f"  **{dt.type_name}** — {dt.description}")
                lines.append(f"    Hints: {', '.join(dt.classification_hints[:5])}")
                for sub_name, sub_def in dt.subtypes.items():
                    lines.append(f"    - {sub_name}: {sub_def.description}")
                    lines.append(f"      Hints: {', '.join(sub_def.classification_hints[:5])}")
            lines.append("")

        return "\n".join(lines)

    def to_extraction_prompt(self, qualified_name: str, subtype: str | None = None) -> str:
        """Generate an LLM extraction prompt for a specific doc type.

        Returns a prompt listing all entity fields to extract with their
        types and descriptions.
        """
        dt = self.get(qualified_name)
        if not dt:
            return f"Unknown document type: {qualified_name}"

        template = dt.get_full_entity_template(subtype)
        lines = [
            f"Extract the following structured fields from this {dt.description}.",
            "Return JSON with these fields (use null for fields you cannot find):",
            "",
        ]

        for name, field_def in template.fields.items():
            req = " (REQUIRED)" if field_def.required else ""
            hint = f" — Hint: {field_def.extraction_hint}" if field_def.extraction_hint else ""
            enum_vals = f" — Values: {', '.join(field_def.enum_values)}" if field_def.enum_values else ""
            lines.append(f"  {name} ({field_def.type}){req}: {field_def.description}{enum_vals}{hint}")

        if template.extraction_prompt:
            lines.append("")
            lines.append(template.extraction_prompt)

        return "\n".join(lines)


# ── Built-in types ───────────────────────────────────────────────────────────


def _build_builtins() -> list[DocTypeDef]:
    """Build all built-in document type definitions."""
    types: list[DocTypeDef] = []

    # ── FINANCIAL ─────────────────────────────────────────────────────

    types.append(DocTypeDef(
        category=DocCategory.FINANCIAL,
        type_name="invoice",
        description="Commercial invoice or bill for goods/services",
        classification_hints=["Invoice", "Bill To", "Amount Due", "Payment Terms", "Tax Invoice",
                              "Invoice Number", "PO Number", "Net 30", "Due Date"],
        subtypes={
            "standard": DocSubtypeDef(
                name="standard", description="Standard commercial invoice",
                classification_hints=["Invoice", "Bill To", "Amount Due"],
            ),
            "credit_note": DocSubtypeDef(
                name="credit_note", description="Credit note or refund document",
                classification_hints=["Credit Note", "Credit Memo", "Refund", "Credited Amount"],
                extra_fields={
                    "original_invoice_ref": EntityFieldDef(
                        type="string", description="Reference to the original invoice being credited"),
                    "credit_reason": EntityFieldDef(
                        type="string", description="Reason for the credit"),
                },
            ),
            "proforma": DocSubtypeDef(
                name="proforma", description="Proforma invoice (pre-shipment estimate)",
                classification_hints=["Proforma", "Pro Forma", "Estimate", "Quotation Invoice"],
            ),
            "debit_note": DocSubtypeDef(
                name="debit_note", description="Debit note for additional charges",
                classification_hints=["Debit Note", "Debit Memo", "Additional Charges"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "invoice_number": EntityFieldDef(type="string", description="Invoice identifier", required=True),
                "invoice_date": EntityFieldDef(type="date", description="Date the invoice was issued", required=True),
                "due_date": EntityFieldDef(type="date", description="Payment due date"),
                "vendor_name": EntityFieldDef(type="string", description="Vendor/supplier name", required=True),
                "buyer_name": EntityFieldDef(type="string", description="Buyer/customer name"),
                "total_amount": EntityFieldDef(type="money", description="Total invoice amount", required=True),
                "currency": EntityFieldDef(type="string", description="Currency code (USD, EUR, etc.)"),
                "tax_amount": EntityFieldDef(type="money", description="Tax amount"),
                "payment_terms": EntityFieldDef(type="string", description="Payment terms (Net 30, Net 60, etc.)"),
                "po_reference": EntityFieldDef(type="string", description="Purchase order reference number"),
                "line_items": EntityFieldDef(type="list", description="List of line items with description, qty, unit price, amount"),
                "status": EntityFieldDef(
                    type="enum", description="Invoice status",
                    enum_values=["draft", "sent", "paid", "overdue", "disputed", "cancelled"]),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single invoice understanding",
                group_by=["doc_id"],
                context_prompt="Summarize this invoice: key line items, total amount, payment terms, any unusual charges or discrepancies.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Invoice ↔ PO ↔ Contract matching",
                group_by=["po_reference", "vendor_name"],
                link_strategy=LinkStrategy(
                    match_fields=["po_reference", "vendor_name"],
                    match_types=["financial.purchase_order", "legal.contract"],
                    relationship="references",
                ),
                context_prompt="Compare this invoice against its PO and contract: do quantities, prices, and terms match? Flag any discrepancies.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full vendor invoice history",
                group_by=["vendor_name"],
                link_strategy=LinkStrategy(
                    match_fields=["vendor_name"],
                    match_types=["financial.invoice", "legal.contract", "communication.email"],
                    relationship="same_entity",
                ),
                context_prompt="Build a complete picture of this vendor: total spend, payment patterns, contract compliance, communication history.",
            ),
        },
        queryable_as="invoice_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.FINANCIAL,
        type_name="bank_statement",
        description="Bank account statement showing transactions and balances",
        classification_hints=["Bank Statement", "Account Statement", "Beginning Balance",
                              "Ending Balance", "Transaction History", "Account Number"],
        subtypes={
            "checking": DocSubtypeDef(
                name="checking", description="Checking/current account statement",
                classification_hints=["Checking Account", "Current Account"],
            ),
            "savings": DocSubtypeDef(
                name="savings", description="Savings account statement",
                classification_hints=["Savings Account", "Interest Earned"],
            ),
            "credit_card": DocSubtypeDef(
                name="credit_card", description="Credit card statement",
                classification_hints=["Credit Card Statement", "Minimum Payment", "APR", "Credit Limit"],
                extra_fields={
                    "credit_limit": EntityFieldDef(type="money", description="Credit limit"),
                    "minimum_payment": EntityFieldDef(type="money", description="Minimum payment due"),
                    "apr": EntityFieldDef(type="numeric", description="Annual percentage rate"),
                },
            ),
            "investment": DocSubtypeDef(
                name="investment", description="Investment/brokerage account statement",
                classification_hints=["Investment Statement", "Portfolio", "Securities", "Brokerage"],
                extra_fields={
                    "portfolio_value": EntityFieldDef(type="money", description="Total portfolio value"),
                    "gain_loss": EntityFieldDef(type="money", description="Unrealized gain/loss"),
                },
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "account_holder": EntityFieldDef(type="string", description="Account holder name", required=True),
                "account_number": EntityFieldDef(type="string", description="Account number (masked)"),
                "institution": EntityFieldDef(type="string", description="Bank/institution name", required=True),
                "statement_period_start": EntityFieldDef(type="date", description="Statement period start date"),
                "statement_period_end": EntityFieldDef(type="date", description="Statement period end date"),
                "opening_balance": EntityFieldDef(type="money", description="Opening/beginning balance"),
                "closing_balance": EntityFieldDef(type="money", description="Closing/ending balance"),
                "total_credits": EntityFieldDef(type="money", description="Total deposits/credits"),
                "total_debits": EntityFieldDef(type="money", description="Total withdrawals/debits"),
                "currency": EntityFieldDef(type="string", description="Currency code"),
                "transaction_count": EntityFieldDef(type="integer", description="Number of transactions"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single statement analysis",
                group_by=["doc_id"],
                context_prompt="Analyze this bank statement: key transactions, unusual activity, balance trends within the period.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Month-over-month trends",
                group_by=["account_number", "institution"],
                link_strategy=LinkStrategy(
                    match_fields=["account_number", "institution"],
                    match_types=["financial.bank_statement"],
                    temporal_window="12m",
                    relationship="same_entity",
                ),
                context_prompt="Compare this statement with previous months: balance trends, recurring transactions, spending pattern changes.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full financial profile",
                group_by=["account_holder"],
                link_strategy=LinkStrategy(
                    match_fields=["account_holder"],
                    match_types=["financial.bank_statement", "financial.tax_return", "financial.invoice"],
                    relationship="same_entity",
                ),
                context_prompt="Build a complete financial picture for this account holder across all accounts and financial documents.",
            ),
        },
        queryable_as="bank_statement_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.FINANCIAL,
        type_name="tax_return",
        description="Tax return filing or supporting tax document",
        classification_hints=["Tax Return", "Form 1040", "W-2", "1099", "K-1", "Schedule C",
                              "Adjusted Gross Income", "Taxable Income", "Filing Status", "IRS"],
        subtypes={
            "1040": DocSubtypeDef(
                name="1040", description="US individual income tax return (Form 1040)",
                classification_hints=["Form 1040", "U.S. Individual Income Tax Return", "Filing Status"],
                extra_fields={
                    "filing_status": EntityFieldDef(
                        type="enum", description="Filing status",
                        enum_values=["single", "married_filing_jointly", "married_filing_separately",
                                     "head_of_household", "qualifying_surviving_spouse"]),
                    "adjusted_gross_income": EntityFieldDef(type="money", description="Adjusted gross income (AGI)"),
                    "taxable_income": EntityFieldDef(type="money", description="Taxable income"),
                    "total_tax": EntityFieldDef(type="money", description="Total tax liability"),
                    "refund_amount": EntityFieldDef(type="money", description="Refund or amount owed"),
                },
            ),
            "w2": DocSubtypeDef(
                name="w2", description="Wage and Tax Statement (W-2)",
                classification_hints=["W-2", "Wage and Tax Statement", "Employer", "Federal income tax withheld"],
                extra_fields={
                    "employer_name": EntityFieldDef(type="string", description="Employer name"),
                    "wages": EntityFieldDef(type="money", description="Wages, tips, other compensation"),
                    "federal_tax_withheld": EntityFieldDef(type="money", description="Federal income tax withheld"),
                },
            ),
            "1099": DocSubtypeDef(
                name="1099", description="Information return (1099-MISC, 1099-NEC, 1099-INT, etc.)",
                classification_hints=["1099", "Nonemployee Compensation", "Interest Income", "Dividend Income"],
                extra_fields={
                    "form_variant": EntityFieldDef(type="string", description="Specific 1099 variant (MISC, NEC, INT, DIV, etc.)"),
                    "payer_name": EntityFieldDef(type="string", description="Payer/issuer name"),
                    "reported_amount": EntityFieldDef(type="money", description="Total reported amount"),
                },
            ),
            "k1": DocSubtypeDef(
                name="k1", description="Partner's Share of Income (Schedule K-1)",
                classification_hints=["K-1", "Schedule K-1", "Partner's Share", "Partnership"],
            ),
            "schedule_c": DocSubtypeDef(
                name="schedule_c", description="Profit or Loss From Business (Schedule C)",
                classification_hints=["Schedule C", "Profit or Loss", "Self-Employment", "Business Income"],
                extra_fields={
                    "business_name": EntityFieldDef(type="string", description="Business name"),
                    "gross_income": EntityFieldDef(type="money", description="Gross income/receipts"),
                    "net_profit": EntityFieldDef(type="money", description="Net profit or loss"),
                },
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "taxpayer_name": EntityFieldDef(type="string", description="Taxpayer name", required=True),
                "tax_year": EntityFieldDef(type="integer", description="Tax year", required=True),
                "ssn_last4": EntityFieldDef(type="string", description="Last 4 digits of SSN (if visible)"),
                "total_income": EntityFieldDef(type="money", description="Total income reported"),
                "total_deductions": EntityFieldDef(type="money", description="Total deductions"),
                "filing_date": EntityFieldDef(type="date", description="Date filed or received"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single tax document analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this tax document: key income sources, deductions, credits, effective tax rate, notable items.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Tax year document set",
                group_by=["taxpayer_name", "tax_year"],
                link_strategy=LinkStrategy(
                    match_fields=["taxpayer_name", "tax_year"],
                    match_types=["financial.tax_return"],
                    relationship="references",
                ),
                context_prompt="How do the supporting documents (W-2s, 1099s, K-1s, receipts) relate to the tax return? Identify any discrepancies or missing documents.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full tax profile across years",
                group_by=["taxpayer_name"],
                link_strategy=LinkStrategy(
                    match_fields=["taxpayer_name"],
                    match_types=["financial.tax_return", "financial.receipt"],
                    relationship="same_entity",
                ),
                context_prompt="Build a multi-year tax profile: income trends, filing patterns, major deductions, estimated tax obligations.",
            ),
        },
        queryable_as="tax_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.FINANCIAL,
        type_name="receipt",
        description="Purchase receipt or expense record",
        classification_hints=["Receipt", "Transaction", "Total", "Subtotal", "Thank you for your purchase",
                              "Merchant", "Payment Method"],
        subtypes={
            "purchase": DocSubtypeDef(
                name="purchase", description="Retail or online purchase receipt",
                classification_hints=["Receipt", "Purchase", "Store", "Order Confirmation"],
            ),
            "expense": DocSubtypeDef(
                name="expense", description="Business expense receipt",
                classification_hints=["Expense", "Business", "Receipt", "Reimbursement"],
                extra_fields={
                    "expense_category": EntityFieldDef(
                        type="enum", description="Expense category",
                        enum_values=["travel", "meals", "supplies", "equipment", "software",
                                     "professional_services", "utilities", "other"]),
                    "project_code": EntityFieldDef(type="string", description="Project or cost center code"),
                },
            ),
            "reimbursement": DocSubtypeDef(
                name="reimbursement", description="Reimbursement request or approval",
                classification_hints=["Reimbursement", "Expense Report", "Approve", "Reimburse"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "merchant_name": EntityFieldDef(type="string", description="Merchant/vendor name", required=True),
                "transaction_date": EntityFieldDef(type="date", description="Transaction date", required=True),
                "total_amount": EntityFieldDef(type="money", description="Total amount", required=True),
                "currency": EntityFieldDef(type="string", description="Currency code"),
                "payment_method": EntityFieldDef(type="string", description="Payment method (card, cash, etc.)"),
                "items": EntityFieldDef(type="list", description="Purchased items with descriptions and amounts"),
                "tax_amount": EntityFieldDef(type="money", description="Tax amount"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single receipt",
                group_by=["doc_id"],
                context_prompt="Summarize this receipt: merchant, items purchased, total, payment method.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Related expense group",
                group_by=["merchant_name"],
                link_strategy=LinkStrategy(
                    match_fields=["merchant_name"],
                    match_types=["financial.receipt"],
                    temporal_window="90d",
                    relationship="same_entity",
                ),
                context_prompt="Group receipts from this merchant: spending pattern, frequency, category.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Spending profile",
                group_by=["expense_category"],
                link_strategy=LinkStrategy(
                    match_fields=["expense_category"],
                    match_types=["financial.receipt", "financial.bank_statement"],
                    relationship="same_entity",
                ),
                context_prompt="Build a spending profile by category: total spend, trends, largest purchases.",
            ),
        },
        queryable_as="receipt_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.FINANCIAL,
        type_name="purchase_order",
        description="Purchase order for goods or services",
        classification_hints=["Purchase Order", "PO Number", "Ship To", "Bill To",
                              "Deliver To", "Order Quantity", "Requisition"],
        subtypes={
            "standard": DocSubtypeDef(
                name="standard", description="Standard one-time purchase order",
                classification_hints=["Purchase Order", "PO", "Order"],
            ),
            "blanket": DocSubtypeDef(
                name="blanket", description="Blanket/standing purchase order for recurring purchases",
                classification_hints=["Blanket Order", "Standing Order", "Framework Order"],
                extra_fields={
                    "valid_from": EntityFieldDef(type="date", description="Blanket order start date"),
                    "valid_to": EntityFieldDef(type="date", description="Blanket order end date"),
                    "max_amount": EntityFieldDef(type="money", description="Maximum order amount"),
                },
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "po_number": EntityFieldDef(type="string", description="Purchase order number", required=True),
                "order_date": EntityFieldDef(type="date", description="Order date", required=True),
                "vendor_name": EntityFieldDef(type="string", description="Vendor/supplier name", required=True),
                "buyer_name": EntityFieldDef(type="string", description="Buyer/requestor name"),
                "total_amount": EntityFieldDef(type="money", description="Total order amount", required=True),
                "currency": EntityFieldDef(type="string", description="Currency code"),
                "delivery_date": EntityFieldDef(type="date", description="Expected delivery date"),
                "line_items": EntityFieldDef(type="list", description="Ordered items with qty, unit price"),
                "approval_status": EntityFieldDef(
                    type="enum", description="Approval status",
                    enum_values=["draft", "pending_approval", "approved", "sent", "received", "cancelled"]),
                "contract_reference": EntityFieldDef(type="string", description="Associated contract reference"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single PO analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this purchase order: items, quantities, pricing, delivery terms.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="PO ↔ Invoice ↔ Contract match",
                group_by=["po_number"],
                link_strategy=LinkStrategy(
                    match_fields=["po_number", "vendor_name"],
                    match_types=["financial.invoice", "legal.contract"],
                    relationship="references",
                ),
                context_prompt="Match this PO against invoices and contracts: are quantities, prices, and terms consistent?",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Vendor ordering history",
                group_by=["vendor_name"],
                link_strategy=LinkStrategy(
                    match_fields=["vendor_name"],
                    match_types=["financial.purchase_order", "financial.invoice", "legal.contract"],
                    relationship="same_entity",
                ),
                context_prompt="Build a complete vendor ordering profile: order frequency, spend, delivery performance.",
            ),
        },
        queryable_as="purchase_order_doc",
    ))

    # ── LEGAL ─────────────────────────────────────────────────────────

    types.append(DocTypeDef(
        category=DocCategory.LEGAL,
        type_name="contract",
        description="Legal agreement between parties",
        classification_hints=["Agreement", "Contract", "Party", "Whereas", "Terms and Conditions",
                              "Governing Law", "Effective Date", "Term", "Termination"],
        subtypes={
            "msa": DocSubtypeDef(
                name="msa", description="Master Service Agreement",
                classification_hints=["Master Service Agreement", "MSA", "General Terms", "Framework Agreement"],
            ),
            "sow": DocSubtypeDef(
                name="sow", description="Statement of Work",
                classification_hints=["Statement of Work", "SOW", "Scope of Work", "Deliverables", "Milestones"],
                extra_fields={
                    "scope_description": EntityFieldDef(type="string", description="Scope of work description"),
                    "deliverables": EntityFieldDef(type="list", description="List of deliverables"),
                    "milestones": EntityFieldDef(type="list", description="Payment or delivery milestones"),
                    "parent_contract_ref": EntityFieldDef(type="string", description="Parent MSA reference"),
                },
            ),
            "amendment": DocSubtypeDef(
                name="amendment", description="Contract amendment or modification",
                classification_hints=["Amendment", "Modification", "Addendum", "Revised", "Amended and Restated"],
                extra_fields={
                    "original_contract_ref": EntityFieldDef(type="string", description="Original contract reference"),
                    "changed_clauses": EntityFieldDef(type="list", description="Clauses modified by this amendment"),
                    "amendment_number": EntityFieldDef(type="integer", description="Amendment sequence number"),
                },
            ),
            "nda": DocSubtypeDef(
                name="nda", description="Non-Disclosure Agreement",
                classification_hints=["Non-Disclosure", "NDA", "Confidentiality", "Confidential Information"],
                extra_fields={
                    "confidentiality_period": EntityFieldDef(type="duration", description="Duration of confidentiality obligation"),
                    "disclosing_party": EntityFieldDef(type="string", description="Party disclosing information"),
                    "receiving_party": EntityFieldDef(type="string", description="Party receiving information"),
                },
            ),
            "lease": DocSubtypeDef(
                name="lease", description="Lease or rental agreement",
                classification_hints=["Lease", "Rental Agreement", "Landlord", "Tenant", "Premises", "Monthly Rent"],
                extra_fields={
                    "property_address": EntityFieldDef(type="string", description="Property/premises address"),
                    "monthly_rent": EntityFieldDef(type="money", description="Monthly rental amount"),
                    "security_deposit": EntityFieldDef(type="money", description="Security deposit amount"),
                },
            ),
            "employment": DocSubtypeDef(
                name="employment", description="Employment agreement or offer letter",
                classification_hints=["Employment Agreement", "Offer Letter", "Compensation", "Benefits",
                                      "Start Date", "Position", "At-Will"],
                extra_fields={
                    "position_title": EntityFieldDef(type="string", description="Job title/position"),
                    "base_salary": EntityFieldDef(type="money", description="Base salary/compensation"),
                    "start_date": EntityFieldDef(type="date", description="Employment start date"),
                },
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "contract_title": EntityFieldDef(type="string", description="Contract title or name", required=True),
                "party_a": EntityFieldDef(type="string", description="First party name", required=True),
                "party_b": EntityFieldDef(type="string", description="Second party name", required=True),
                "effective_date": EntityFieldDef(type="date", description="Effective date", required=True),
                "expiry_date": EntityFieldDef(type="date", description="Expiration or end date"),
                "total_value": EntityFieldDef(type="money", description="Total contract value"),
                "currency": EntityFieldDef(type="string", description="Currency code"),
                "auto_renewal": EntityFieldDef(type="boolean", description="Whether contract auto-renews"),
                "renewal_notice_days": EntityFieldDef(type="integer", description="Days notice required for non-renewal"),
                "governing_law": EntityFieldDef(type="string", description="Governing law jurisdiction"),
                "termination_clause": EntityFieldDef(type="string", description="Key termination conditions"),
                "payment_terms": EntityFieldDef(type="string", description="Payment terms"),
                "key_clauses": EntityFieldDef(type="list", description="List of key clause summaries"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single contract analysis",
                group_by=["doc_id"],
                context_prompt="Analyze this contract: parties, key terms, obligations, payment structure, renewal/termination conditions, notable or unusual clauses.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Contract family (MSA → SOW → Amendments)",
                group_by=["party_a", "party_b", "contract_title"],
                link_strategy=LinkStrategy(
                    match_fields=["party_a", "party_b"],
                    match_types=["legal.contract"],
                    relationship="parent_child",
                ),
                context_prompt="Map the contract family: MSA, SOWs, amendments. Track how terms evolved across amendments. Identify any conflicting clauses.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full counterparty legal relationship",
                group_by=["party_b"],
                link_strategy=LinkStrategy(
                    match_fields=["party_b"],
                    match_types=["legal.contract", "financial.invoice", "financial.purchase_order", "communication.email"],
                    relationship="same_entity",
                ),
                context_prompt="Build the complete relationship profile with this counterparty: all contracts, commercial activity, compliance status, communication history.",
            ),
        },
        queryable_as="contract_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.LEGAL,
        type_name="policy",
        description="Internal or regulatory policy document",
        classification_hints=["Policy", "Guidelines", "Procedure", "Compliance", "Regulation",
                              "Effective Date", "Scope", "Applicability", "Violations"],
        subtypes={
            "procurement": DocSubtypeDef(
                name="procurement", description="Procurement/purchasing policy",
                classification_hints=["Procurement Policy", "Purchasing", "Vendor Selection", "Approval Authority"],
            ),
            "hr": DocSubtypeDef(
                name="hr", description="Human resources policy",
                classification_hints=["HR Policy", "Employee", "Leave", "Benefits", "Conduct"],
            ),
            "security": DocSubtypeDef(
                name="security", description="Information security policy",
                classification_hints=["Security Policy", "Data Protection", "Access Control", "Incident Response"],
            ),
            "compliance": DocSubtypeDef(
                name="compliance", description="Regulatory compliance policy",
                classification_hints=["Compliance", "Regulatory", "SOX", "GDPR", "HIPAA", "Anti-Corruption"],
            ),
            "travel": DocSubtypeDef(
                name="travel", description="Travel and expense policy",
                classification_hints=["Travel Policy", "Per Diem", "Expense Limits", "Booking", "Reimbursement"],
            ),
            "financial": DocSubtypeDef(
                name="financial", description="Financial/accounting policy",
                classification_hints=["Financial Policy", "Accounting", "Revenue Recognition", "Budgeting"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "policy_name": EntityFieldDef(type="string", description="Policy name/title", required=True),
                "version": EntityFieldDef(type="string", description="Policy version number"),
                "effective_date": EntityFieldDef(type="date", description="When the policy takes effect"),
                "review_date": EntityFieldDef(type="date", description="Next scheduled review date"),
                "owner": EntityFieldDef(type="string", description="Policy owner (person or department)"),
                "scope": EntityFieldDef(type="string", description="Who/what the policy applies to"),
                "key_rules": EntityFieldDef(type="list", description="Key rules, thresholds, and requirements"),
                "approval_matrix": EntityFieldDef(type="list", description="Approval thresholds and authorities"),
                "penalties": EntityFieldDef(type="list", description="Consequences for violations"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single policy analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this policy: scope, key rules, thresholds, approval requirements, consequences.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Policy version history",
                group_by=["policy_name"],
                link_strategy=LinkStrategy(
                    match_fields=["policy_name"],
                    match_types=["legal.policy"],
                    relationship="parent_child",
                ),
                context_prompt="Track how this policy evolved: what changed between versions, what was tightened or relaxed.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full policy compliance landscape",
                group_by=["scope"],
                link_strategy=LinkStrategy(
                    match_fields=["scope"],
                    match_types=["legal.policy", "operational.report"],
                    relationship="same_entity",
                ),
                context_prompt="Map all policies applicable to this scope: overlaps, gaps, conflicting rules.",
            ),
        },
        queryable_as="policy_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.LEGAL,
        type_name="agreement",
        description="Terms of service, SLA, MOU, or other formal agreement",
        classification_hints=["Terms of Service", "SLA", "Service Level Agreement", "Memorandum of Understanding",
                              "MOU", "Privacy Policy", "Terms and Conditions"],
        subtypes={
            "tos": DocSubtypeDef(
                name="tos", description="Terms of Service / Terms and Conditions",
                classification_hints=["Terms of Service", "Terms and Conditions", "User Agreement", "Terms of Use"],
            ),
            "sla": DocSubtypeDef(
                name="sla", description="Service Level Agreement",
                classification_hints=["SLA", "Service Level", "Uptime", "Response Time", "Availability"],
                extra_fields={
                    "sla_metrics": EntityFieldDef(type="list", description="SLA metrics (uptime %, response time, etc.)"),
                    "penalties_for_breach": EntityFieldDef(type="list", description="Penalties for SLA breaches"),
                },
            ),
            "mou": DocSubtypeDef(
                name="mou", description="Memorandum of Understanding",
                classification_hints=["MOU", "Memorandum of Understanding", "Intent", "Non-Binding"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "agreement_title": EntityFieldDef(type="string", description="Agreement title", required=True),
                "parties": EntityFieldDef(type="list", description="Parties involved", required=True),
                "effective_date": EntityFieldDef(type="date", description="Effective date"),
                "term_duration": EntityFieldDef(type="duration", description="Agreement duration"),
                "key_obligations": EntityFieldDef(type="list", description="Key obligations for each party"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single agreement analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this agreement: parties, obligations, metrics, term, key conditions.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Agreement + amendments",
                group_by=["agreement_title", "parties"],
                link_strategy=LinkStrategy(
                    match_fields=["agreement_title"],
                    match_types=["legal.agreement", "legal.contract"],
                    relationship="parent_child",
                ),
                context_prompt="Map this agreement family and any related contracts or amendments.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full party agreement landscape",
                group_by=["parties"],
                link_strategy=LinkStrategy(
                    match_fields=["parties"],
                    relationship="same_entity",
                ),
                context_prompt="All agreements with this party: compliance status, obligations, renewal dates.",
            ),
        },
        queryable_as="agreement_doc",
    ))

    # ── COMMUNICATION ─────────────────────────────────────────────────

    types.append(DocTypeDef(
        category=DocCategory.COMMUNICATION,
        type_name="email",
        description="Email message with optional attachments",
        classification_hints=["From:", "To:", "Subject:", "Date:", "Cc:", "Re:", "Fwd:"],
        subtypes={
            "vendor_comm": DocSubtypeDef(
                name="vendor_comm", description="Communication with external vendor/supplier",
                classification_hints=["vendor", "supplier", "quote", "proposal", "pricing", "delivery"],
            ),
            "internal": DocSubtypeDef(
                name="internal", description="Internal organizational communication",
                classification_hints=["team", "meeting", "update", "FYI", "action items"],
            ),
            "notification": DocSubtypeDef(
                name="notification", description="Automated notification or alert",
                classification_hints=["notification", "alert", "automated", "system", "no-reply"],
            ),
            "approval": DocSubtypeDef(
                name="approval", description="Approval request or decision",
                classification_hints=["approve", "approval", "sign off", "authorize", "reject", "pending review"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "from_address": EntityFieldDef(type="string", description="Sender email address", required=True),
                "from_name": EntityFieldDef(type="string", description="Sender display name"),
                "to_addresses": EntityFieldDef(type="list", description="Recipient email addresses", required=True),
                "cc_addresses": EntityFieldDef(type="list", description="CC recipients"),
                "subject": EntityFieldDef(type="string", description="Email subject line", required=True),
                "date_sent": EntityFieldDef(type="date", description="Date sent", required=True),
                "thread_id": EntityFieldDef(type="string", description="Email thread/conversation ID"),
                "has_attachments": EntityFieldDef(type="boolean", description="Whether email has attachments"),
                "attachment_names": EntityFieldDef(type="list", description="Names of attached files"),
                "intent": EntityFieldDef(
                    type="enum", description="Primary intent of the message",
                    enum_values=["information", "question", "request", "approval_request",
                                 "approval_decision", "escalation", "follow_up", "introduction",
                                 "complaint", "thank_you", "scheduling"]),
                "action_items": EntityFieldDef(type="list", description="Action items identified in the email"),
                "sentiment": EntityFieldDef(
                    type="enum", description="Overall sentiment",
                    enum_values=["positive", "neutral", "negative", "urgent"]),
                "referenced_entities": EntityFieldDef(type="list", description="People, companies, projects, docs mentioned"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single email analysis",
                group_by=["doc_id"],
                context_prompt="Analyze this email: intent, key information, action items, sentiment, referenced entities (people, projects, documents).",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Email thread + referenced docs",
                group_by=["thread_id"],
                link_strategy=LinkStrategy(
                    match_fields=["thread_id", "referenced_entities"],
                    match_types=["communication.email", "legal.contract", "financial.invoice"],
                    relationship="references",
                ),
                context_prompt="Reconstruct the full conversation thread: who said what, decisions made, action items across all messages. Link to any referenced documents.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full communication history with contact/entity",
                group_by=["referenced_entities"],
                link_strategy=LinkStrategy(
                    match_fields=["from_address", "to_addresses", "referenced_entities"],
                    match_types=["communication.email", "communication.chat_thread"],
                    relationship="same_entity",
                ),
                context_prompt="Build the complete communication history with this person/entity: topics discussed, decisions made, open items, relationship trajectory.",
            ),
        },
        message_intents=[
            MessageIntentDef(
                intent="approval_request", description="Requesting approval or sign-off",
                indicators=["please approve", "for your approval", "sign off", "review and approve", "pending your approval"],
                link_to_types=["legal.contract", "financial.invoice", "financial.purchase_order"],
                action_required=True,
            ),
            MessageIntentDef(
                intent="question", description="Asking a question that needs an answer",
                indicators=["?", "could you", "can you clarify", "what is", "when will", "how do"],
                action_required=True,
            ),
            MessageIntentDef(
                intent="escalation", description="Escalating an issue or concern",
                indicators=["escalate", "urgent", "critical", "unresolved", "need immediate", "overdue"],
                link_to_types=["financial.invoice", "legal.contract"],
                action_required=True,
            ),
            MessageIntentDef(
                intent="decision", description="Communicating a decision",
                indicators=["decided", "approved", "rejected", "we will go with", "final decision"],
                link_to_types=["legal.contract", "financial.purchase_order"],
            ),
            MessageIntentDef(
                intent="information", description="Sharing information (FYI)",
                indicators=["FYI", "for your information", "just wanted to share", "update", "heads up"],
            ),
            MessageIntentDef(
                intent="follow_up", description="Following up on a previous item",
                indicators=["following up", "any update", "checking in", "circling back", "reminder"],
                action_required=True,
            ),
        ],
        queryable_as="email_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.COMMUNICATION,
        type_name="chat_thread",
        description="Chat conversation thread from Slack, Google Chat, Teams, etc.",
        classification_hints=["#channel", "thread", "replied", "reaction", "mention", "@"],
        subtypes={
            "slack": DocSubtypeDef(
                name="slack", description="Slack channel or DM thread",
                classification_hints=["Slack", "#", "channel", "workspace"],
            ),
            "gchat": DocSubtypeDef(
                name="gchat", description="Google Chat conversation",
                classification_hints=["Google Chat", "Hangouts", "Space"],
            ),
            "teams": DocSubtypeDef(
                name="teams", description="Microsoft Teams conversation",
                classification_hints=["Teams", "Microsoft Teams", "channel"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "channel_name": EntityFieldDef(type="string", description="Channel or space name"),
                "thread_id": EntityFieldDef(type="string", description="Thread identifier", required=True),
                "participants": EntityFieldDef(type="list", description="People in the conversation", required=True),
                "start_date": EntityFieldDef(type="date", description="When the thread started"),
                "message_count": EntityFieldDef(type="integer", description="Number of messages in thread"),
                "topic": EntityFieldDef(type="string", description="Inferred topic of discussion"),
                "decisions": EntityFieldDef(type="list", description="Decisions made in the thread"),
                "action_items": EntityFieldDef(type="list", description="Action items identified"),
                "intent": EntityFieldDef(
                    type="enum", description="Primary thread intent",
                    enum_values=["discussion", "decision", "question", "planning",
                                 "incident", "announcement", "social"]),
                "referenced_entities": EntityFieldDef(type="list", description="People, projects, docs mentioned"),
                "files_shared": EntityFieldDef(type="list", description="Files shared in the thread"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single thread analysis",
                group_by=["thread_id"],
                context_prompt="Analyze this chat thread: topic, key decisions, action items, who said what. Identify any documents, projects, or entities referenced.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Related threads + referenced docs",
                group_by=["topic", "referenced_entities"],
                link_strategy=LinkStrategy(
                    match_fields=["referenced_entities", "topic"],
                    match_types=["communication.chat_thread", "communication.email"],
                    temporal_window="30d",
                    relationship="references",
                ),
                context_prompt="Connect this thread to related conversations and documents: what's the broader context? Are there open items from other threads?",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full entity/project context from chats",
                group_by=["referenced_entities"],
                link_strategy=LinkStrategy(
                    match_fields=["referenced_entities"],
                    relationship="same_entity",
                ),
                context_prompt="Build the complete discussion history around this entity/project: decisions made, open questions, action items, stakeholders involved.",
            ),
        },
        message_intents=[
            MessageIntentDef(
                intent="decision", description="A decision was made in the thread",
                indicators=["let's go with", "decided", "approved", "we'll do", "final call"],
            ),
            MessageIntentDef(
                intent="question", description="Someone is asking for input",
                indicators=["?", "thoughts?", "anyone know", "can someone", "what do you think"],
                action_required=True,
            ),
            MessageIntentDef(
                intent="incident", description="Reporting or discussing an incident",
                indicators=["down", "broken", "incident", "outage", "alert", "P0", "P1"],
                action_required=True,
            ),
            MessageIntentDef(
                intent="planning", description="Planning or coordination",
                indicators=["plan", "schedule", "timeline", "sprint", "roadmap", "next steps"],
            ),
        ],
        queryable_as="chat_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.COMMUNICATION,
        type_name="meeting_notes",
        description="Meeting notes, minutes, or transcript",
        classification_hints=["Meeting Notes", "Minutes", "Attendees", "Agenda", "Action Items",
                              "Discussion", "Next Steps"],
        subtypes={
            "standup": DocSubtypeDef(
                name="standup", description="Daily standup or sync meeting",
                classification_hints=["Standup", "Daily Sync", "Yesterday", "Today", "Blockers"],
            ),
            "review": DocSubtypeDef(
                name="review", description="Review meeting (design, code, business)",
                classification_hints=["Review", "Demo", "Feedback", "Retrospective"],
            ),
            "planning": DocSubtypeDef(
                name="planning", description="Planning or strategy meeting",
                classification_hints=["Planning", "Strategy", "Roadmap", "Quarterly", "OKR"],
            ),
            "one_on_one": DocSubtypeDef(
                name="one_on_one", description="1:1 meeting notes",
                classification_hints=["1:1", "One on One", "1-on-1", "Check-in"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "meeting_title": EntityFieldDef(type="string", description="Meeting title", required=True),
                "meeting_date": EntityFieldDef(type="date", description="Meeting date", required=True),
                "attendees": EntityFieldDef(type="list", description="People who attended", required=True),
                "organizer": EntityFieldDef(type="string", description="Meeting organizer"),
                "agenda_items": EntityFieldDef(type="list", description="Agenda topics"),
                "decisions": EntityFieldDef(type="list", description="Decisions made"),
                "action_items": EntityFieldDef(type="list", description="Action items with owners and due dates"),
                "key_discussion_points": EntityFieldDef(type="list", description="Key discussion points"),
                "next_meeting_date": EntityFieldDef(type="date", description="Next meeting date if scheduled"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single meeting analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this meeting: key decisions, action items with owners, important discussion points.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Meeting series",
                group_by=["meeting_title", "attendees"],
                link_strategy=LinkStrategy(
                    match_fields=["meeting_title", "attendees"],
                    match_types=["communication.meeting_notes"],
                    temporal_window="90d",
                    relationship="same_entity",
                ),
                context_prompt="Track this meeting series: recurring themes, action item completion, evolving decisions.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Project/team meeting history",
                group_by=["attendees"],
                link_strategy=LinkStrategy(
                    match_fields=["attendees"],
                    match_types=["communication.meeting_notes", "communication.email"],
                    relationship="same_entity",
                ),
                context_prompt="Build a meeting history for this team/project: decisions over time, open action items, key themes.",
            ),
        },
        queryable_as="meeting_doc",
    ))

    # ── OPERATIONAL ───────────────────────────────────────────────────

    types.append(DocTypeDef(
        category=DocCategory.OPERATIONAL,
        type_name="report",
        description="Business or technical report",
        classification_hints=["Report", "Analysis", "Findings", "Recommendations", "Executive Summary",
                              "Audit", "Assessment", "Results"],
        subtypes={
            "audit": DocSubtypeDef(
                name="audit", description="Audit report (internal or external)",
                classification_hints=["Audit", "Internal Audit", "External Audit", "Findings", "Observations"],
                extra_fields={
                    "audit_type": EntityFieldDef(type="string", description="Type of audit"),
                    "findings_count": EntityFieldDef(type="integer", description="Number of findings"),
                    "critical_findings": EntityFieldDef(type="integer", description="Number of critical findings"),
                },
            ),
            "analysis": DocSubtypeDef(
                name="analysis", description="Analysis or research report",
                classification_hints=["Analysis", "Research", "Study", "Assessment", "Evaluation"],
            ),
            "status": DocSubtypeDef(
                name="status", description="Status or progress report",
                classification_hints=["Status Report", "Progress", "Weekly Update", "Monthly Report", "Dashboard"],
            ),
            "incident": DocSubtypeDef(
                name="incident", description="Incident or post-mortem report",
                classification_hints=["Incident", "Post-Mortem", "Root Cause", "Outage", "RCA"],
                extra_fields={
                    "severity": EntityFieldDef(
                        type="enum", description="Incident severity",
                        enum_values=["critical", "high", "medium", "low"]),
                    "root_cause": EntityFieldDef(type="string", description="Root cause analysis"),
                    "resolution": EntityFieldDef(type="string", description="Resolution steps taken"),
                    "prevention_actions": EntityFieldDef(type="list", description="Actions to prevent recurrence"),
                },
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "report_title": EntityFieldDef(type="string", description="Report title", required=True),
                "report_date": EntityFieldDef(type="date", description="Report date", required=True),
                "author": EntityFieldDef(type="string", description="Report author"),
                "report_period": EntityFieldDef(type="string", description="Period covered (Q1 2025, Jan 2025, etc.)"),
                "summary": EntityFieldDef(type="string", description="Executive summary"),
                "findings": EntityFieldDef(type="list", description="Key findings"),
                "recommendations": EntityFieldDef(type="list", description="Recommendations"),
                "metrics": EntityFieldDef(type="list", description="Key metrics reported"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single report analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this report: key findings, metrics, recommendations, action items.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Report series (quarterly, monthly)",
                group_by=["report_title"],
                link_strategy=LinkStrategy(
                    match_fields=["report_title", "author"],
                    match_types=["operational.report"],
                    temporal_window="1y",
                    relationship="same_entity",
                ),
                context_prompt="Track this report series: trend in findings, metrics over time, recurring recommendations.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Domain/project report landscape",
                group_by=["author"],
                link_strategy=LinkStrategy(
                    match_fields=["author"],
                    match_types=["operational.report", "legal.policy"],
                    relationship="same_entity",
                ),
                context_prompt="All reports for this domain: cumulative findings, metrics trends, open recommendations.",
            ),
        },
        queryable_as="report_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.OPERATIONAL,
        type_name="specification",
        description="Technical or business specification document",
        classification_hints=["Specification", "Requirements", "Design", "Architecture", "Technical Spec",
                              "PRD", "RFC", "Functional Requirements"],
        subtypes={
            "technical": DocSubtypeDef(
                name="technical", description="Technical design or architecture specification",
                classification_hints=["Technical Spec", "Architecture", "System Design", "RFC", "ADR"],
            ),
            "requirements": DocSubtypeDef(
                name="requirements", description="Business or product requirements document",
                classification_hints=["Requirements", "PRD", "User Stories", "Acceptance Criteria", "BRD"],
            ),
            "design": DocSubtypeDef(
                name="design", description="Design document (UI/UX, system, etc.)",
                classification_hints=["Design Doc", "Wireframe", "Mockup", "Design System", "UX Spec"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "spec_title": EntityFieldDef(type="string", description="Specification title", required=True),
                "version": EntityFieldDef(type="string", description="Version number"),
                "author": EntityFieldDef(type="string", description="Author"),
                "date": EntityFieldDef(type="date", description="Document date"),
                "status": EntityFieldDef(
                    type="enum", description="Document status",
                    enum_values=["draft", "review", "approved", "deprecated"]),
                "key_requirements": EntityFieldDef(type="list", description="Key requirements or design decisions"),
                "dependencies": EntityFieldDef(type="list", description="Dependencies on other systems or specs"),
                "constraints": EntityFieldDef(type="list", description="Technical or business constraints"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single spec analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this specification: scope, key requirements, constraints, dependencies.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Spec versions and related specs",
                group_by=["spec_title"],
                link_strategy=LinkStrategy(
                    match_fields=["spec_title", "dependencies"],
                    match_types=["operational.specification"],
                    relationship="parent_child",
                ),
                context_prompt="Track spec evolution: what changed between versions, how do related specs interact.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Project spec landscape",
                group_by=["dependencies"],
                link_strategy=LinkStrategy(
                    match_fields=["dependencies"],
                    match_types=["operational.specification", "operational.report"],
                    relationship="same_entity",
                ),
                context_prompt="All specs for this project/product: coverage, gaps, conflicting requirements.",
            ),
        },
        queryable_as="spec_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.OPERATIONAL,
        type_name="procedure",
        description="Standard operating procedure, runbook, or checklist",
        classification_hints=["SOP", "Procedure", "Runbook", "Checklist", "Step-by-Step",
                              "Instructions", "Workflow", "How To"],
        subtypes={
            "sop": DocSubtypeDef(
                name="sop", description="Standard Operating Procedure",
                classification_hints=["SOP", "Standard Operating Procedure", "Procedure"],
            ),
            "runbook": DocSubtypeDef(
                name="runbook", description="Operational runbook",
                classification_hints=["Runbook", "Operations", "Playbook", "Troubleshooting"],
            ),
            "checklist": DocSubtypeDef(
                name="checklist", description="Verification or process checklist",
                classification_hints=["Checklist", "Verification", "Quality Check", "Inspection"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "procedure_name": EntityFieldDef(type="string", description="Procedure name", required=True),
                "version": EntityFieldDef(type="string", description="Version number"),
                "owner": EntityFieldDef(type="string", description="Process owner"),
                "last_updated": EntityFieldDef(type="date", description="Last updated date"),
                "steps": EntityFieldDef(type="list", description="Procedure steps"),
                "prerequisites": EntityFieldDef(type="list", description="Prerequisites"),
                "roles_involved": EntityFieldDef(type="list", description="Roles/people involved"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single procedure analysis",
                group_by=["doc_id"],
                context_prompt="Summarize this procedure: purpose, steps, roles, prerequisites.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Procedure versions",
                group_by=["procedure_name"],
                link_strategy=LinkStrategy(
                    match_fields=["procedure_name"],
                    match_types=["operational.procedure"],
                    relationship="parent_child",
                ),
                context_prompt="Track procedure evolution: what changed, why, any gaps in current version.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Domain procedure set",
                group_by=["owner"],
                link_strategy=LinkStrategy(
                    match_fields=["owner", "roles_involved"],
                    match_types=["operational.procedure", "legal.policy"],
                    relationship="same_entity",
                ),
                context_prompt="All procedures for this domain: coverage, consistency with policies, gaps.",
            ),
        },
        queryable_as="procedure_doc",
    ))

    # ── PERSONAL ──────────────────────────────────────────────────────

    types.append(DocTypeDef(
        category=DocCategory.PERSONAL,
        type_name="identity",
        description="Identity document (passport, license, ID card, visa)",
        classification_hints=["Passport", "Driver's License", "ID Card", "Visa", "Social Security",
                              "Birth Certificate", "Nationality", "Date of Birth"],
        subtypes={
            "passport": DocSubtypeDef(
                name="passport", description="Passport",
                classification_hints=["Passport", "Nationality", "Machine Readable Zone", "MRZ"],
            ),
            "license": DocSubtypeDef(
                name="license", description="Driver's license or state ID",
                classification_hints=["Driver's License", "State ID", "DMV", "Class", "Endorsements"],
            ),
            "visa": DocSubtypeDef(
                name="visa", description="Travel or work visa",
                classification_hints=["Visa", "Work Permit", "Consulate", "Entry", "Valid Until"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "holder_name": EntityFieldDef(type="string", description="Document holder name", required=True),
                "document_number": EntityFieldDef(type="string", description="Document number"),
                "issuing_authority": EntityFieldDef(type="string", description="Issuing authority/country"),
                "issue_date": EntityFieldDef(type="date", description="Issue date"),
                "expiry_date": EntityFieldDef(type="date", description="Expiration date"),
                "nationality": EntityFieldDef(type="string", description="Nationality/citizenship"),
                "date_of_birth": EntityFieldDef(type="date", description="Date of birth"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single ID document",
                group_by=["doc_id"],
                context_prompt="Extract key details from this identity document: holder, document number, validity, issuer.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="All IDs for person",
                group_by=["holder_name"],
                link_strategy=LinkStrategy(
                    match_fields=["holder_name"],
                    match_types=["personal.identity"],
                    relationship="same_entity",
                ),
                context_prompt="All identity documents for this person: which are current, which are expiring.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Person identity profile",
                group_by=["holder_name"],
                link_strategy=LinkStrategy(
                    match_fields=["holder_name"],
                    relationship="same_entity",
                ),
                context_prompt="Complete identity profile for this person across all document types.",
            ),
        },
        queryable_as="identity_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.PERSONAL,
        type_name="medical",
        description="Medical or health-related document",
        classification_hints=["Medical", "Prescription", "Lab Results", "Diagnosis", "Healthcare",
                              "Patient", "Doctor", "Hospital", "Insurance Claim"],
        subtypes={
            "prescription": DocSubtypeDef(
                name="prescription", description="Medical prescription",
                classification_hints=["Prescription", "Rx", "Medication", "Dosage", "Refill"],
            ),
            "lab_result": DocSubtypeDef(
                name="lab_result", description="Laboratory test results",
                classification_hints=["Lab Results", "Test Results", "Blood Work", "Panel", "Reference Range"],
            ),
            "insurance_claim": DocSubtypeDef(
                name="insurance_claim", description="Health insurance claim or EOB",
                classification_hints=["Insurance Claim", "EOB", "Explanation of Benefits", "Copay", "Deductible"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "patient_name": EntityFieldDef(type="string", description="Patient name", required=True),
                "provider_name": EntityFieldDef(type="string", description="Healthcare provider/doctor"),
                "facility": EntityFieldDef(type="string", description="Hospital/clinic name"),
                "date": EntityFieldDef(type="date", description="Date of service/test", required=True),
                "diagnosis": EntityFieldDef(type="list", description="Diagnoses or conditions"),
                "medications": EntityFieldDef(type="list", description="Medications prescribed"),
                "test_results": EntityFieldDef(type="list", description="Test results with values"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single medical record",
                group_by=["doc_id"],
                context_prompt="Summarize this medical document: conditions, treatments, test results, follow-up needed.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Treatment timeline",
                group_by=["patient_name", "diagnosis"],
                link_strategy=LinkStrategy(
                    match_fields=["patient_name"],
                    match_types=["personal.medical"],
                    temporal_window="1y",
                    relationship="same_entity",
                ),
                context_prompt="Track treatment timeline: progression of conditions, medication changes, test result trends.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full health profile",
                group_by=["patient_name"],
                link_strategy=LinkStrategy(
                    match_fields=["patient_name"],
                    match_types=["personal.medical", "financial.receipt"],
                    relationship="same_entity",
                ),
                context_prompt="Complete health profile: conditions, treatments, providers, insurance claims.",
            ),
        },
        queryable_as="medical_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.PERSONAL,
        type_name="education",
        description="Educational document (transcript, certificate, degree)",
        classification_hints=["Transcript", "Certificate", "Degree", "Diploma", "GPA",
                              "University", "College", "Graduation", "Semester"],
        subtypes={
            "transcript": DocSubtypeDef(
                name="transcript", description="Academic transcript",
                classification_hints=["Transcript", "GPA", "Credits", "Courses", "Semester"],
            ),
            "certificate": DocSubtypeDef(
                name="certificate", description="Professional or academic certificate",
                classification_hints=["Certificate", "Certification", "Completed", "Awarded"],
            ),
            "degree": DocSubtypeDef(
                name="degree", description="Degree or diploma",
                classification_hints=["Degree", "Diploma", "Bachelor", "Master", "PhD", "Conferred"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "student_name": EntityFieldDef(type="string", description="Student name", required=True),
                "institution": EntityFieldDef(type="string", description="Educational institution", required=True),
                "program": EntityFieldDef(type="string", description="Degree program or course name"),
                "date_awarded": EntityFieldDef(type="date", description="Date awarded or completed"),
                "gpa": EntityFieldDef(type="numeric", description="GPA or grade"),
                "honors": EntityFieldDef(type="string", description="Honors or distinction"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single education document",
                group_by=["doc_id"],
                context_prompt="Summarize this educational document: institution, program, achievements.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Academic history",
                group_by=["student_name", "institution"],
                link_strategy=LinkStrategy(
                    match_fields=["student_name"],
                    match_types=["personal.education"],
                    relationship="same_entity",
                ),
                context_prompt="Build the academic timeline: degrees, certifications, progression.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Full education profile",
                group_by=["student_name"],
                link_strategy=LinkStrategy(
                    match_fields=["student_name"],
                    relationship="same_entity",
                ),
                context_prompt="Complete education and certification profile for this person.",
            ),
        },
        queryable_as="education_doc",
    ))

    # ── REFERENCE ─────────────────────────────────────────────────────

    types.append(DocTypeDef(
        category=DocCategory.REFERENCE,
        type_name="wiki",
        description="Knowledge base article, FAQ, how-to guide, or glossary entry",
        classification_hints=["Wiki", "Knowledge Base", "FAQ", "How To", "Guide", "Glossary",
                              "Documentation", "Help Article"],
        subtypes={
            "knowledge_base": DocSubtypeDef(
                name="knowledge_base", description="Knowledge base article",
                classification_hints=["Knowledge Base", "KB", "Article", "Solution"],
            ),
            "faq": DocSubtypeDef(
                name="faq", description="Frequently asked questions",
                classification_hints=["FAQ", "Frequently Asked", "Q&A", "Questions"],
            ),
            "how_to": DocSubtypeDef(
                name="how_to", description="How-to or tutorial",
                classification_hints=["How To", "Tutorial", "Guide", "Step by Step", "Getting Started"],
            ),
            "glossary": DocSubtypeDef(
                name="glossary", description="Glossary or terminology reference",
                classification_hints=["Glossary", "Terminology", "Definitions", "Terms"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "title": EntityFieldDef(type="string", description="Article title", required=True),
                "author": EntityFieldDef(type="string", description="Author"),
                "last_updated": EntityFieldDef(type="date", description="Last updated date"),
                "topics": EntityFieldDef(type="list", description="Topics or tags"),
                "summary": EntityFieldDef(type="string", description="Brief summary"),
                "audience": EntityFieldDef(type="string", description="Target audience"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single article",
                group_by=["doc_id"],
                context_prompt="Summarize this article: topic, key information, applicability.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Related articles",
                group_by=["topics"],
                link_strategy=LinkStrategy(
                    match_fields=["topics"],
                    match_types=["reference.wiki"],
                    relationship="references",
                ),
                context_prompt="How does this article relate to others on the same topic? Identify gaps or overlaps.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Knowledge domain graph",
                group_by=["topics"],
                link_strategy=LinkStrategy(
                    match_fields=["topics"],
                    relationship="same_entity",
                ),
                context_prompt="Build the knowledge map for this domain: coverage, gaps, outdated content.",
            ),
        },
        queryable_as="wiki_doc",
    ))

    types.append(DocTypeDef(
        category=DocCategory.REFERENCE,
        type_name="manual",
        description="Product manual, user guide, or API documentation",
        classification_hints=["Manual", "User Guide", "API Documentation", "Reference Guide",
                              "Product Documentation", "Installation Guide", "Configuration"],
        subtypes={
            "product": DocSubtypeDef(
                name="product", description="Product manual or user guide",
                classification_hints=["Product Manual", "User Guide", "User Manual", "Quick Start"],
            ),
            "api_doc": DocSubtypeDef(
                name="api_doc", description="API documentation",
                classification_hints=["API", "Endpoint", "REST", "GraphQL", "SDK", "Developer"],
            ),
        },
        entity_template=EntityTemplate(
            fields={
                "title": EntityFieldDef(type="string", description="Manual/guide title", required=True),
                "product_name": EntityFieldDef(type="string", description="Product or service name"),
                "version": EntityFieldDef(type="string", description="Documentation version"),
                "last_updated": EntityFieldDef(type="date", description="Last updated date"),
                "sections": EntityFieldDef(type="list", description="Major sections or chapters"),
            },
        ),
        context_tiers={
            "t1": ContextTierDef(
                tier="t1", scope="document", description="Single manual/guide",
                group_by=["doc_id"],
                context_prompt="Summarize this documentation: scope, key topics, target audience.",
            ),
            "t2": ContextTierDef(
                tier="t2", scope="cross_document", description="Documentation versions",
                group_by=["product_name", "title"],
                link_strategy=LinkStrategy(
                    match_fields=["product_name"],
                    match_types=["reference.manual"],
                    relationship="parent_child",
                ),
                context_prompt="Track documentation versions: what changed, what's new, deprecated features.",
            ),
            "t3": ContextTierDef(
                tier="t3", scope="entity", description="Product documentation set",
                group_by=["product_name"],
                link_strategy=LinkStrategy(
                    match_fields=["product_name"],
                    match_types=["reference.manual", "reference.wiki"],
                    relationship="same_entity",
                ),
                context_prompt="Complete documentation landscape for this product: coverage, gaps, consistency.",
            ),
        },
        queryable_as="manual_doc",
    ))

    return types


# ── Singleton accessor ───────────────────────────────────────────────────────


def get_registry() -> DocTypeRegistry:
    """Get the default registry with all built-in types loaded.

    The registry is created once and cached at module level.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = DocTypeRegistry()
        _default_registry.register_many(_build_builtins())
    return _default_registry
