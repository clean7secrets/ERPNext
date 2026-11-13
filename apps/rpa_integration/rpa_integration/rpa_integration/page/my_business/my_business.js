// My Business: the client's simple home for Online Books.
// Plain words, big buttons, short forms. Everything calls rpa_integration.books_api.

const API = "rpa_integration.books_api.";
const inr = (v) => format_currency(v || 0, "INR");
const PDF = (doctype, name, fmt) =>
	`/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent(doctype)}` +
	`&name=${encodeURIComponent(name)}&format=${encodeURIComponent(fmt)}&no_letterhead=1`;

frappe.pages["my-business"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("My Business"), single_column: true });
	wrapper.mb = new MyBusiness(page, $(wrapper).find(".layout-main-section"));
};

frappe.pages["my-business"].on_page_show = function (wrapper) {
	wrapper.mb && wrapper.mb.load();
};

class MyBusiness {
	constructor(page, $body) {
		this.page = page;
		this.$body = $body;
		this.opts = null;
		page.set_secondary_action(__("Invoice style"), () => this.style_dialog(), "brush");
		page.add_inner_button(__("Language"), () => this.language_dialog());
		this.$body.html(`<div class="mb-wrap"><div class="text-muted">${__("Loading your books…")}</div></div>`);
		this.load();
	}

	async load() {
		const r = await frappe.call({ method: API + "dashboard" });
		this.data = r.message;
		this.render();
	}

	has(feature) {
		return (this.data.features || []).includes(feature);
	}

	render() {
		const d = this.data;
		const n = d.numbers;
		this.page.set_title(d.company);
		const actions = [
			["new-invoice", "file-text", __("New invoice"), true],
			["receive", "wallet", __("Receive money"), true],
			["new-quote", "file", __("New quote"), true],
			["new-customer", "users", __("Add customer"), true],
			["new-product", "package", __("Add product or service"), true],
			["expense", "credit-card", __("Record expense"), this.has("accounting")],
			["upload", "upload", __("Upload a bill"), this.has("accounting") || this.has("purchase")],
			["purchase-bill", "file-plus", __("New purchase bill"), this.has("purchase")],
			["pay", "send", __("Pay supplier"), this.has("purchase")],
			["new-supplier", "truck", __("Add supplier"), this.has("purchase")],
			["stock-in", "arrow-down", __("Stock in"), this.has("inventory")],
			["stock-out", "arrow-up", __("Stock out"), this.has("inventory")],
			["stock-count", "list", __("Stock count"), this.has("inventory")],
		].filter((a) => a[3]);
		const cards = [
			[__("Sales this month"), inr(n.sales_month)],
			[__("Money to collect"), inr(n.to_collect) + (n.overdue ? ` <span class="mb-overdue">${n.overdue} ${__("overdue")}</span>` : "")],
			[__("Received this month"), inr(n.received_month)],
		];
		if (this.has("accounting")) cards.push([__("Expenses this month"), inr(n.expenses_month)]);
		if (this.has("purchase")) cards.push([__("Money to pay"), inr(n.to_pay)]);
		if (this.has("inventory")) cards.push([__("Stock value"), inr(n.stock_value)]);

		const status = (r) => {
			if (r.docstatus === 0) return `<span class="mb-pill mb-grey">${__("Draft")}</span>`;
			if (r.docstatus === 2) return `<span class="mb-pill mb-grey">${__("Cancelled")}</span>`;
			if (r.is_return) return `<span class="mb-pill mb-grey">${__("Credit note")}</span>`;
			if (r.outstanding_amount <= 0) return `<span class="mb-pill mb-green">${__("Paid")}</span>`;
			if (r.status === "Overdue") return `<span class="mb-pill mb-orange">${__("Overdue")}</span>`;
			return `<span class="mb-pill mb-blue">${__("Due")} ${inr(r.outstanding_amount)}</span>`;
		};
		const rows = (d.recent || []).map((r) => `
			<tr>
				<td><a href="/app/sales-invoice/${encodeURIComponent(r.name)}">${frappe.utils.escape_html(r.name)}</a></td>
				<td>${frappe.utils.escape_html(r.customer_name || "")}</td>
				<td>${frappe.datetime.str_to_user(r.posting_date)}</td>
				<td class="text-right">${inr(r.grand_total)}</td>
				<td>${status(r)}</td>
				<td class="text-right mb-row-actions">
					<a class="btn btn-xs btn-default" target="_blank" href="${PDF("Sales Invoice", r.name, "Books Invoice - My style")}">${__("PDF")}</a>
					${r.docstatus === 1 && r.outstanding_amount > 0 && !r.is_return
						? `<button class="btn btn-xs btn-primary" data-receive="${frappe.utils.escape_html(r.name)}">${__("Receive")}</button>` : ""}
				</td>
			</tr>`).join("");
		const reports = this.has("accounting")
			? `<div class="mb-links">
				<a href="/app/query-report/Profit and Loss Statement">${__("Profit and loss")}</a>
				<a href="/app/query-report/Balance Sheet">${__("Balance sheet")}</a>
				<a href="/app/query-report/Accounts Receivable">${__("Who owes me")}</a>
				<a href="/app/query-report/General Ledger">${__("Ledger")}</a>
			   </div>` : "";

		this.$body.html(`
		<div class="mb-wrap">
			<div class="mb-hello">${__("Hello")} ${frappe.utils.escape_html(d.first_name || "")} 👋</div>
			${d.has_address ? "" : `<div class="mb-notice">${__("Add your business address once so it prints on your invoices.")}
				<button class="btn btn-sm btn-primary" data-act="address">${__("Add address")}</button></div>`}
			<div class="mb-actions">${actions.map((a) => `
				<button class="mb-action" data-act="${a[0]}">${frappe.utils.icon(a[1], "lg")}<span>${a[2]}</span></button>`).join("")}
			</div>
			<div class="mb-cards">${cards.map((c) => `<div class="mb-card"><div class="mb-card-label">${c[0]}</div><div class="mb-card-value">${c[1]}</div></div>`).join("")}</div>
			${reports}
			${this.uploads_html()}
			${this.bills_html()}
			<div class="mb-section">
				<div class="mb-section-head"><h4>${__("Recent invoices")}</h4>
					<span><a href="/app/sales-invoice">${__("All invoices")}</a> · <a href="/app/quotation">${__("Quotes")}</a> ·
					<a href="/app/customer">${__("Customers")}</a> · <a href="/app/item">${__("Products")}</a></span></div>
				${rows ? `<div class="table-responsive"><table class="table mb-table"><thead><tr>
					<th>${__("Invoice")}</th><th>${__("Customer")}</th><th>${__("Date")}</th><th class="text-right">${__("Amount")}</th><th>${__("Status")}</th><th></th>
					</tr></thead><tbody>${rows}</tbody></table></div>`
					: `<div class="mb-empty">${__("No invoices yet. Start with")} <b>${__("New invoice")}</b>.</div>`}
			</div>
		</div>`);

		this.$body.find("[data-act]").on("click", (e) => {
			const act = $(e.currentTarget).attr("data-act");
			({
				"new-invoice": () => this.doc_dialog("invoice"),
				"new-quote": () => this.doc_dialog("quote"),
				receive: () => this.receive_dialog(),
				"new-customer": () => this.customer_dialog(),
				"new-product": () => this.product_dialog(),
				expense: () => this.expense_dialog(),
				upload: () => this.upload_dialog(),
				"purchase-bill": () => this.purchase_dialog(),
				pay: () => this.pay_dialog(),
				"new-supplier": () => this.supplier_dialog(),
				"stock-in": () => this.stock_dialog("in"),
				"stock-out": () => this.stock_dialog("out"),
				"stock-count": () => this.stock_dialog("count"),
				address: () => this.address_dialog(),
			})[act]();
		});
		this.$body.find("[data-receive]").on("click", (e) => this.receive_dialog($(e.currentTarget).attr("data-receive")));
		this.$body.find("[data-enter]").on("click", (e) => this.enter_upload_dialog($(e.currentTarget).attr("data-enter")));
		this.$body.find("[data-enter-bill]").on("click", (e) => {
			const up = (this.data.uploads || []).find((u) => u.name === $(e.currentTarget).attr("data-enter-bill")) || {};
			this.purchase_dialog(up);
		});
		this.$body.find("[data-pay]").on("click", (e) => this.pay_dialog($(e.currentTarget).attr("data-pay")));
	}

	async options() {
		if (!this.opts) this.opts = (await frappe.call({ method: API + "options" })).message;
		return this.opts;
	}

	// ---------------------------------------------------------------- invoice / quote
	doc_dialog(kind) {
		const is_quote = kind === "quote";
		const d = new frappe.ui.Dialog({
			title: is_quote ? __("New quote") : __("New invoice"),
			size: "large",
			fields: [
				{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer", reqd: 1,
				  description: `<a href="#" class="mb-inline-add">${__("+ Add a new customer")}</a>` },
				{ fieldtype: "Column Break" },
				{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "days", label: is_quote ? __("Valid for (days)") : __("Payment due in (days)"),
				  fieldtype: "Int", default: is_quote ? 30 : 15 },
				{ fieldtype: "Section Break" },
				{ fieldname: "items", label: __("Products or services"), fieldtype: "Table", reqd: 1, in_place_edit: true,
				  data: [{ qty: 1 }], fields: [
					{ fieldname: "item_code", label: __("Product or service"), fieldtype: "Link", options: "Item", in_list_view: 1, reqd: 1, columns: 5,
					  onchange: function () { // fill the usual rate
						const row = this.doc || {};
						if (!row.item_code) return;
						frappe.db.get_value("Item", row.item_code, "standard_rate").then((r) => {
							if (r.message && r.message.standard_rate && !row.rate) { row.rate = r.message.standard_rate; d.fields_dict.items.grid.refresh(); }
						});
					  } },
					{ fieldname: "qty", label: __("Qty"), fieldtype: "Float", default: 1, in_list_view: 1, columns: 2 },
					{ fieldname: "rate", label: __("Rate"), fieldtype: "Currency", in_list_view: 1, columns: 2 },
					{ fieldname: "discount", label: __("Disc. %"), fieldtype: "Percent", in_list_view: 1, columns: 1 },
				] },
				{ fieldname: "add_product", fieldtype: "HTML", options: `<a href="#" class="mb-add-product">${__("+ Add a new product or service")}</a>` },
				{ fieldname: "notes", label: __("Note on the invoice (optional)"), fieldtype: "Small Text" },
			],
			primary_action_label: is_quote ? __("Save quote") : __("Save & finalise"),
			primary_action: async (v) => {
				const items = (v.items || []).filter((i) => i.item_code);
				const r = await frappe.call({
					method: API + (is_quote ? "create_quote" : "create_invoice"), freeze: true,
					freeze_message: __("Saving…"),
					args: is_quote
						? { customer: v.customer, items, transaction_date: v.date, valid_days: v.days, notes: v.notes }
						: { customer: v.customer, items, posting_date: v.date, due_days: v.days, notes: v.notes },
				});
				d.hide();
				this.after_save(is_quote ? "Quotation" : "Sales Invoice", r.message);
			},
		});
		d.$wrapper.find(".mb-inline-add").on("click", (e) => { e.preventDefault(); this.customer_dialog((c) => d.set_value("customer", c.name)); });
		d.$wrapper.find(".mb-add-product").on("click", (e) => {
			e.preventDefault();
			this.product_dialog((p) => {
				const grid = d.fields_dict.items.grid;
				const rows = grid.get_data();
				const empty = rows.find((r) => !r.item_code);
				if (empty) Object.assign(empty, { item_code: p.name, qty: 1, rate: p.rate });
				else rows.push({ item_code: p.name, qty: 1, rate: p.rate });
				grid.refresh();
			});
		});
		d.show();
	}

	after_save(doctype, res) {
		const fmt = doctype === "Quotation" ? "Books Quote - My style" : "Books Invoice - My style";
		const what = doctype === "Quotation" ? __("Quote") : __("Invoice");
		const d = new frappe.ui.Dialog({
			title: `${what} ${res.name} ${__("saved")}`,
			fields: [{ fieldtype: "HTML", options: `
				<p>${__("Total")}: <b>${inr(res.grand_total)}</b></p>
				<div class="mb-after">
					<a class="btn btn-primary" target="_blank" href="${PDF(doctype, res.name, fmt)}">${__("Download PDF")}</a>
					<a class="btn btn-default" target="_blank" href="https://wa.me/?text=${encodeURIComponent(`${what} ${res.name}: ${inr(res.grand_total)}`)}">${__("Share on WhatsApp")}</a>
					<a class="btn btn-default" href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(res.name)}">${__("Open")}</a>
				</div>` }],
			primary_action_label: doctype === "Sales Invoice" && res.docstatus === 1 ? __("Receive money now") : __("Done"),
			primary_action: () => {
				d.hide();
				if (doctype === "Sales Invoice" && res.docstatus === 1) this.receive_dialog(res.name);
			},
		});
		d.show();
		this.load();
	}

	// ---------------------------------------------------------------- money in / out
	receive_dialog(invoice) {
		const d = new frappe.ui.Dialog({
			title: __("Receive money"),
			fields: [
				{ fieldname: "invoice", label: __("Invoice"), fieldtype: "Link", options: "Sales Invoice", reqd: 1, default: invoice,
				  get_query: () => ({ filters: { docstatus: 1, outstanding_amount: [">", 0] } }),
				  onchange: () => {
					const inv = d.get_value("invoice");
					inv && frappe.db.get_value("Sales Invoice", inv, ["outstanding_amount", "customer_name"]).then((r) => {
						d.set_value("amount", r.message.outstanding_amount);
						d.set_df_property("amount", "description", `${r.message.customer_name} · ${__("due")} ${inr(r.message.outstanding_amount)}`);
					});
				  } },
				{ fieldname: "amount", label: __("Amount received"), fieldtype: "Currency", reqd: 1 },
				{ fieldname: "mode", label: __("How was it paid?"), fieldtype: "Select", options: ["Cash", "UPI", "Bank transfer", "Cheque"].join("\n"), default: "UPI" },
				{ fieldname: "reference", label: __("UTR / cheque no. (optional)"), fieldtype: "Data", depends_on: "eval:doc.mode!='Cash'" },
				{ fieldname: "date", label: __("Date received"), fieldtype: "Date", default: frappe.datetime.get_today() },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "receive_money", freeze: true,
					args: { invoice: v.invoice, amount: v.amount, mode: v.mode, payment_date: v.date, reference: v.reference } });
				d.hide();
				frappe.show_alert({ message: __("Payment saved"), indicator: "green" });
				this.load();
			},
		});
		d.show();
		if (invoice) d.fields_dict.invoice.df.onchange();
	}

	async expense_dialog() {
		const o = await this.options();
		const d = new frappe.ui.Dialog({
			title: __("Record expense"),
			fields: [
				{ fieldname: "category", label: __("What was it for?"), fieldtype: "Select", options: (o.expense_accounts || []).join("\n"), reqd: 1 },
				{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1 },
				{ fieldname: "paid_from", label: __("Paid from"), fieldtype: "Select", options: "Cash\nBank", default: "Bank" },
				{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
				{ fieldname: "note", label: __("Note (optional)"), fieldtype: "Data" },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "record_expense", freeze: true,
					args: { category: v.category, amount: v.amount, paid_from: v.paid_from, expense_date: v.date, note: v.note } });
				d.hide();
				frappe.show_alert({ message: __("Expense saved"), indicator: "green" });
				this.load();
			},
		});
		d.show();
	}

	// ---------------------------------------------------------------- masters
	async customer_dialog(done) {
		const o = await this.options();
		const d = new frappe.ui.Dialog({
			title: __("Add customer"),
			fields: [
				{ fieldname: "customer_name", label: __("Name"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "gstin", label: __("GSTIN (if registered)"), fieldtype: "Data", length: 15 },
				{ fieldtype: "Column Break" },
				{ fieldname: "phone", label: __("Mobile"), fieldtype: "Data", options: "Phone" },
				{ fieldname: "email", label: __("Email"), fieldtype: "Data", options: "Email" },
				{ fieldtype: "Section Break", label: __("Billing address") },
				{ fieldname: "address_line1", label: __("Address"), fieldtype: "Data" },
				{ fieldname: "city", label: __("City"), fieldtype: "Data" },
				{ fieldtype: "Column Break" },
				{ fieldname: "state", label: __("State"), fieldtype: o.states.length ? "Select" : "Data", options: ["", ...o.states].join("\n") },
				{ fieldname: "pincode", label: __("PIN code"), fieldtype: "Data", length: 6 },
			],
			primary_action_label: __("Save customer"),
			primary_action: async (v) => {
				const r = await frappe.call({ method: API + "create_customer", freeze: true, args: v });
				d.hide();
				frappe.show_alert({ message: __("Customer added"), indicator: "green" });
				done ? done(r.message) : this.load();
			},
		});
		d.show();
	}

	async product_dialog(done) {
		const o = await this.options();
		const d = new frappe.ui.Dialog({
			title: __("Add product or service"),
			fields: [
				{ fieldname: "item_name", label: __("Name"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "is_service", label: __("This is a service"), fieldtype: "Check" },
				{ fieldname: "rate", label: __("Usual selling rate (before GST)"), fieldtype: "Currency" },
				{ fieldtype: "Column Break" },
				{ fieldname: "hsn", label: __("HSN / SAC code"), fieldtype: "Data", reqd: 1,
				  description: __("Goods: HSN (e.g. 68022190). Services: SAC starting with 99.") },
				{ fieldname: "gst_rate", label: __("GST rate %"), fieldtype: "Select", options: o.gst_rates.join("\n"), default: "18" },
				{ fieldname: "unit", label: __("Unit"), fieldtype: "Select", options: o.uoms.join("\n"), default: "Nos" },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				const r = await frappe.call({ method: API + "create_product", freeze: true, args: v });
				d.hide();
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				done ? done(r.message) : this.load();
			},
		});
		d.show();
	}

	async address_dialog() {
		const o = await this.options();
		const d = new frappe.ui.Dialog({
			title: __("Your business address"),
			fields: [
				{ fieldname: "address_line1", label: __("Address"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "city", label: __("City"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "state", label: __("State"), fieldtype: o.states.length ? "Select" : "Data", options: ["", ...o.states].join("\n"), reqd: 1 },
				{ fieldname: "pincode", label: __("PIN code"), fieldtype: "Data", reqd: 1, length: 6 },
				{ fieldname: "phone", label: __("Phone (optional)"), fieldtype: "Data" },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "save_address", freeze: true, args: v });
				d.hide();
				this.load();
			},
		});
		d.show();
	}

	// ---------------------------------------------------------------- bill uploads
	uploads_html() {
		const ups = this.data.uploads || [];
		if (!ups.length) return "";
		const pill = (st) => st === "New" ? `<span class="mb-pill mb-orange">${__("Waiting to be entered")}</span>`
			: st === "Entered" ? `<span class="mb-pill mb-green">${__("Entered")}</span>` : `<span class="mb-pill mb-grey">${__(st)}</span>`;
		return `<div class="mb-section mb-gap"><div class="mb-section-head"><h4>${__("Uploaded bills")}</h4>
			<a href="/app/rpa-bill-upload">${__("All uploads")}</a></div>
			<table class="table mb-table"><tbody>${ups.map((u) => `<tr>
				<td><a target="_blank" href="${u.bill_file}">${__("View")}</a></td>
				<td>${frappe.utils.escape_html(u.supplier_name || __("Bill"))}</td>
				<td>${u.bill_date ? frappe.datetime.str_to_user(u.bill_date) : ""}</td>
				<td class="text-right">${u.amount ? inr(u.amount) : ""}</td>
				<td>${pill(u.status)}</td>
				<td class="text-right">${u.status === "New" && this.has("accounting")
					? `<button class="btn btn-xs btn-primary" data-enter="${frappe.utils.escape_html(u.name)}">${__("Enter as expense")}</button>` : ""}
					${u.status === "New" && this.has("purchase")
					? `<button class="btn btn-xs btn-default" data-enter-bill="${frappe.utils.escape_html(u.name)}">${__("Enter as purchase bill")}</button>` : ""}</td>
			</tr>`).join("")}</tbody></table>
			<div class="text-muted small">${__("Your CA team can also enter these for you.")}</div></div>`;
	}

	upload_dialog() {
		const d = new frappe.ui.Dialog({
			title: __("Upload a bill"),
			fields: [
				{ fieldname: "file_url", label: __("Photo or PDF of the bill"), fieldtype: "Attach", reqd: 1 },
				{ fieldname: "supplier_name", label: __("Paid to (optional)"), fieldtype: "Data" },
				{ fieldname: "amount", label: __("Amount (optional)"), fieldtype: "Currency" },
				{ fieldtype: "Column Break" },
				{ fieldname: "bill_date", label: __("Bill date"), fieldtype: "Date", default: frappe.datetime.get_today() },
				{ fieldname: "paid_from", label: __("Paid from"), fieldtype: "Select", options: ["", "Cash", "Bank", "Not paid yet"].join("\n") },
				{ fieldname: "note", label: __("Note (optional)"), fieldtype: "Small Text" },
			],
			primary_action_label: __("Upload"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "upload_bill", freeze: true, args: v });
				d.hide();
				frappe.show_alert({ message: __("Bill uploaded"), indicator: "green" });
				this.load();
			},
		});
		d.show();
	}

	async enter_upload_dialog(name) {
		const o = await this.options();
		const up = (this.data.uploads || []).find((u) => u.name === name) || {};
		const d = new frappe.ui.Dialog({
			title: __("Enter as expense"),
			fields: [
				{ fieldname: "category", label: __("What was it for?"), fieldtype: "Select", options: (o.expense_accounts || []).join("\n"), reqd: 1 },
				{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: up.amount },
				{ fieldname: "paid_from", label: __("Paid from"), fieldtype: "Select", options: "Cash\nBank", default: "Bank" },
				{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: up.bill_date || frappe.datetime.get_today() },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "enter_upload_as_expense", freeze: true,
					args: { upload: name, category: v.category, amount: v.amount, paid_from: v.paid_from, expense_date: v.date } });
				d.hide();
				frappe.show_alert({ message: __("Expense saved"), indicator: "green" });
				this.load();
			},
		});
		d.show();
	}

	// ---------------------------------------------------------------- purchase
	bills_html() {
		const bills = this.data.bills || [];
		if (!this.has("purchase")) return "";
		const pill = (b) => b.docstatus !== 1 ? `<span class="mb-pill mb-grey">${__("Draft")}</span>`
			: b.outstanding_amount <= 0 ? `<span class="mb-pill mb-green">${__("Paid")}</span>`
			: `<span class="mb-pill mb-orange">${__("To pay")} ${inr(b.outstanding_amount)}</span>`;
		return `<div class="mb-section mb-gap"><div class="mb-section-head"><h4>${__("Purchase bills")}</h4>
			<span><a href="/app/purchase-invoice">${__("All purchase bills")}</a> · <a href="/app/supplier">${__("Suppliers")}</a></span></div>
			${bills.length ? `<table class="table mb-table"><tbody>${bills.map((b) => `<tr>
				<td><a href="/app/purchase-invoice/${encodeURIComponent(b.name)}">${frappe.utils.escape_html(b.name)}</a></td>
				<td>${frappe.utils.escape_html(b.supplier_name || "")}${b.bill_no ? ` <span class="text-muted small">#${frappe.utils.escape_html(b.bill_no)}</span>` : ""}</td>
				<td>${frappe.datetime.str_to_user(b.posting_date)}</td>
				<td class="text-right">${inr(b.grand_total)}</td><td>${pill(b)}</td>
				<td class="text-right">${b.docstatus === 1 && b.outstanding_amount > 0
					? `<button class="btn btn-xs btn-primary" data-pay="${frappe.utils.escape_html(b.name)}">${__("Pay")}</button>` : ""}</td>
			</tr>`).join("")}</tbody></table>` : `<div class="mb-empty">${__("No purchase bills yet.")}</div>`}</div>`;
	}

	async supplier_dialog(done) {
		const o = await this.options();
		const d = new frappe.ui.Dialog({
			title: __("Add supplier"),
			fields: [
				{ fieldname: "supplier_name", label: __("Name"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "gstin", label: __("GSTIN (if registered)"), fieldtype: "Data", length: 15 },
				{ fieldtype: "Column Break" },
				{ fieldname: "phone", label: __("Mobile"), fieldtype: "Data" },
				{ fieldname: "email", label: __("Email"), fieldtype: "Data", options: "Email" },
				{ fieldtype: "Section Break", label: __("Address") },
				{ fieldname: "address_line1", label: __("Address"), fieldtype: "Data" },
				{ fieldname: "city", label: __("City"), fieldtype: "Data" },
				{ fieldtype: "Column Break" },
				{ fieldname: "state", label: __("State"), fieldtype: o.states.length ? "Select" : "Data", options: ["", ...o.states].join("\n") },
				{ fieldname: "pincode", label: __("PIN code"), fieldtype: "Data", length: 6 },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				const r = await frappe.call({ method: API + "create_supplier", freeze: true, args: v });
				d.hide();
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				done ? done(r.message) : this.load();
			},
		});
		d.show();
	}

	purchase_dialog(upload) {
		upload = upload || {};
		const d = new frappe.ui.Dialog({
			title: __("New purchase bill"),
			size: "large",
			fields: [
				{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier", reqd: 1,
				  description: `<a href="#" class="mb-add-supplier">${__("+ Add a new supplier")}</a>` },
				{ fieldname: "bill_no", label: __("Supplier's bill number"), fieldtype: "Data" },
				{ fieldtype: "Column Break" },
				{ fieldname: "bill_date", label: __("Bill date"), fieldtype: "Date", reqd: 1, default: upload.bill_date || frappe.datetime.get_today() },
				{ fieldname: "due_days", label: __("Pay within (days)"), fieldtype: "Int", default: 30 },
				{ fieldname: "update_stock", label: __("Add these to my stock"), fieldtype: "Check", default: this.has("inventory") ? 1 : 0,
				  hidden: this.has("inventory") ? 0 : 1 },
				{ fieldtype: "Section Break" },
				{ fieldname: "items", label: __("What you bought"), fieldtype: "Table", reqd: 1, in_place_edit: true, data: [{ qty: 1 }], fields: [
					{ fieldname: "item_code", label: __("Product or service"), fieldtype: "Link", options: "Item", in_list_view: 1, reqd: 1, columns: 5 },
					{ fieldname: "qty", label: __("Qty"), fieldtype: "Float", default: 1, in_list_view: 1, columns: 2 },
					{ fieldname: "rate", label: __("Rate"), fieldtype: "Currency", in_list_view: 1, columns: 3 },
				] },
				{ fieldname: "add_product", fieldtype: "HTML", options: `<a href="#" class="mb-add-product">${__("+ Add a new product or service")}</a>` },
				{ fieldname: "hint", fieldtype: "HTML", options: upload.name ? `<div class="text-muted small">${__("From uploaded bill")} ${frappe.utils.escape_html(upload.name)} · <a target="_blank" href="${upload.bill_file}">${__("View")}</a></div>` : "" },
			],
			primary_action_label: __("Save bill"),
			primary_action: async (v) => {
				const r = await frappe.call({ method: API + "create_purchase_bill", freeze: true,
					args: { supplier: v.supplier, items: (v.items || []).filter((i) => i.item_code), bill_no: v.bill_no,
						bill_date: v.bill_date, due_days: v.due_days, upload: upload.name, update_stock: v.update_stock } });
				d.hide();
				frappe.show_alert({ message: `${__("Purchase bill")} ${r.message.name} · ${inr(r.message.grand_total)}`, indicator: "green" });
				this.load();
			},
		});
		d.$wrapper.find(".mb-add-supplier").on("click", (e) => { e.preventDefault(); this.supplier_dialog((s) => d.set_value("supplier", s.name)); });
		d.$wrapper.find(".mb-add-product").on("click", (e) => {
			e.preventDefault();
			this.product_dialog((p) => {
				const grid = d.fields_dict.items.grid; const rows = grid.get_data();
				const empty = rows.find((r) => !r.item_code);
				if (empty) Object.assign(empty, { item_code: p.name, qty: 1, rate: p.rate }); else rows.push({ item_code: p.name, qty: 1, rate: p.rate });
				grid.refresh();
			});
		});
		d.show();
	}

	pay_dialog(bill) {
		const d = new frappe.ui.Dialog({
			title: __("Pay supplier"),
			fields: [
				{ fieldname: "bill", label: __("Purchase bill"), fieldtype: "Link", options: "Purchase Invoice", reqd: 1, default: bill,
				  get_query: () => ({ filters: { docstatus: 1, outstanding_amount: [">", 0] } }),
				  onchange: () => {
					const b = d.get_value("bill");
					b && frappe.db.get_value("Purchase Invoice", b, ["outstanding_amount", "supplier_name"]).then((r) => {
						d.set_value("amount", r.message.outstanding_amount);
						d.set_df_property("amount", "description", `${r.message.supplier_name} · ${__("due")} ${inr(r.message.outstanding_amount)}`);
					});
				  } },
				{ fieldname: "amount", label: __("Amount paid"), fieldtype: "Currency", reqd: 1 },
				{ fieldname: "mode", label: __("How did you pay?"), fieldtype: "Select", options: ["Bank transfer", "UPI", "Cheque", "Cash"].join("\n"), default: "Bank transfer" },
				{ fieldname: "reference", label: __("UTR / cheque no. (optional)"), fieldtype: "Data", depends_on: "eval:doc.mode!='Cash'" },
				{ fieldname: "date", label: __("Date paid"), fieldtype: "Date", default: frappe.datetime.get_today() },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "pay_supplier", freeze: true,
					args: { bill: v.bill, amount: v.amount, mode: v.mode, payment_date: v.date, reference: v.reference } });
				d.hide();
				frappe.show_alert({ message: __("Payment saved"), indicator: "green" });
				this.load();
			},
		});
		d.show();
		if (bill) d.fields_dict.bill.df.onchange();
	}

	// ---------------------------------------------------------------- stock
	async stock_dialog(kind) {
		const stock = (await frappe.call({ method: API + "stock_list" })).message || [];
		const titles = { in: __("Stock in"), out: __("Stock out"), count: __("Stock count") };
		const table = stock.length ? `<table class="table table-sm mb-table"><thead><tr><th>${__("Product")}</th><th class="text-right">${__("In hand")}</th></tr></thead><tbody>
			${stock.slice(0, 12).map((s) => `<tr><td>${frappe.utils.escape_html(s.item_name)}</td><td class="text-right">${s.in_hand} ${frappe.utils.escape_html(s.unit || "")}</td></tr>`).join("")}</tbody></table>` : "";
		const d = new frappe.ui.Dialog({
			title: titles[kind],
			fields: [
				{ fieldname: "item_code", label: __("Product"), fieldtype: "Link", options: "Item", reqd: 1 },
				{ fieldname: "qty", label: kind === "count" ? __("Quantity you counted") : __("Quantity"), fieldtype: "Float", reqd: 1 },
				{ fieldname: "rate", label: __("Cost per unit (optional)"), fieldtype: "Currency", hidden: kind === "out" ? 1 : 0 },
				{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
				{ fieldname: "note", label: __("Note (optional)"), fieldtype: "Data", hidden: kind === "count" ? 1 : 0 },
				{ fieldname: "now", fieldtype: "HTML", options: table },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				const r = kind === "count"
					? await frappe.call({ method: API + "stock_count", freeze: true, args: { item_code: v.item_code, counted_qty: v.qty, rate: v.rate, count_date: v.date } })
					: await frappe.call({ method: API + "stock_move", freeze: true, args: { item_code: v.item_code, qty: v.qty, direction: kind, rate: v.rate, move_date: v.date, note: v.note } });
				d.hide();
				frappe.show_alert({ message: `${__("Saved")} · ${__("In hand")}: ${r.message.in_hand}`, indicator: "green" });
				this.load();
			},
		});
		d.show();
	}

	language_dialog() {
		const d = new frappe.ui.Dialog({
			title: __("Language"),
			fields: [{ fieldname: "lang", label: __("Show my books in"), fieldtype: "Select",
				options: [{ value: "en", label: "English" }, { value: "hi", label: "हिंदी" }, { value: "mr", label: "मराठी" }],
				default: this.data.lang || "en" }],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				await frappe.call({ method: API + "set_language", args: { lang: v.lang } });
				window.location.reload();
			},
		});
		d.show();
	}

	// ---------------------------------------------------------------- invoice style
	async style_dialog() {
		const s = (await frappe.call({ method: API + "get_style" })).message;
		const v = s.values || {};
		const d = new frappe.ui.Dialog({
			title: __("Invoice style"),
			size: "large",
			fields: [
				{ fieldname: "rpa_inv_layout", label: __("Layout"), fieldtype: "Select", options: s.layouts.join("\n"), default: v.rpa_inv_layout || "Classic GST" },
				{ fieldname: "rpa_inv_colour", label: __("Brand colour"), fieldtype: "Color", default: v.rpa_inv_colour || "#003366" },
				{ fieldname: "rpa_inv_font", label: __("Font"), fieldtype: "Select", options: "Sans\nSerif\nRounded", default: v.rpa_inv_font || "Sans" },
				{ fieldname: "rpa_inv_second_language", label: __("Second language (Bilingual layout)"), fieldtype: "Select", options: "Hindi\nMarathi", default: v.rpa_inv_second_language || "Hindi" },
				{ fieldtype: "Column Break" },
				{ fieldname: "rpa_inv_logo", label: __("Logo"), fieldtype: "Attach Image", default: v.rpa_inv_logo },
				{ fieldname: "rpa_inv_signature", label: __("Signature"), fieldtype: "Attach Image", default: v.rpa_inv_signature },
				{ fieldname: "rpa_inv_letterhead_header", label: __("Letterhead header (Letterhead layout)"), fieldtype: "Attach Image", default: v.rpa_inv_letterhead_header },
				{ fieldname: "rpa_inv_letterhead_footer", label: __("Letterhead footer"), fieldtype: "Attach Image", default: v.rpa_inv_letterhead_footer },
				{ fieldtype: "Section Break", label: __("Show on the invoice") },
				{ fieldname: "rpa_inv_show_hsn", label: __("HSN/SAC column and summary"), fieldtype: "Check", default: v.rpa_inv_show_hsn ?? 1 },
				{ fieldname: "rpa_inv_show_discount", label: __("Discount column"), fieldtype: "Check", default: v.rpa_inv_show_discount ?? 1 },
				{ fieldname: "rpa_inv_show_uom", label: __("Unit after quantity"), fieldtype: "Check", default: v.rpa_inv_show_uom ?? 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "rpa_inv_upi_id", label: __("UPI ID (adds a pay-by-QR code)"), fieldtype: "Data", default: v.rpa_inv_upi_id },
				{ fieldtype: "Section Break" },
				{ fieldname: "rpa_inv_bank_details", label: __("Bank details"), fieldtype: "Small Text", default: v.rpa_inv_bank_details },
				{ fieldname: "rpa_inv_terms", label: __("Terms and conditions"), fieldtype: "Small Text", default: v.rpa_inv_terms },
				{ fieldtype: "Column Break" },
				{ fieldname: "rpa_inv_header_note", label: __("Note above items"), fieldtype: "Small Text", default: v.rpa_inv_header_note },
				{ fieldname: "rpa_inv_footer_note", label: __("Footer note"), fieldtype: "Small Text", default: v.rpa_inv_footer_note },
			],
			primary_action_label: __("Save style"),
			primary_action: async (vals) => {
				await frappe.call({ method: API + "save_style", freeze: true, args: { values: vals } });
				d.hide();
				frappe.show_alert({ message: __("Invoice style saved"), indicator: "green" });
				const last = (this.data.recent || []).find((r) => r.docstatus === 1);
				if (last) window.open(PDF("Sales Invoice", last.name, "Books Invoice - My style"), "_blank");
			},
		});
		d.show();
	}
}
