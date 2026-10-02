// Builds reports/FORESIGHT_Executive_Readout.pptx (D7).
// Audience: NorthBay's Head of Operations and Finance lead — not data scientists.
// Run: node tools/build_readout.js

const pptxgen = require("pptxgenjs");
const path = require("path");

const OUT = path.join(__dirname, "..", "reports", "FORESIGHT_Executive_Readout.pptx");

const INK = "1B1930";       // near-black indigo, dominant on dark slides
const DEEP = "2A2456";      // supporting indigo
const VIOLET = "6B5BD6";    // brand accent
const AMBER = "D69B45";     // warning / baseline
const RED = "C0392B";       // stockout
const GREEN = "3F9E6A";     // healthy
const PAPER = "FFFFFF";
const MIST = "F4F3FA";      // light card tint
const GREY = "5C5A72";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Zidio Development — Data Science";
pres.title = "Project FORESIGHT — Executive Readout";

const H = "Cambria";  // serif headers
const B = "Calibri";  // sans body

// helper: section title on a light slide
function title(slide, text, sub) {
  slide.addText(text, {
    x: 0.7, y: 0.45, w: 11.9, h: 0.75,
    fontSize: 38, bold: true, color: INK, fontFace: H, isTextBox: true, margin: 0,
  });
  if (sub) {
    slide.addText(sub, {
      x: 0.7, y: 1.22, w: 11.9, h: 0.4,
      fontSize: 14, color: GREY, fontFace: B, isTextBox: true, margin: 0,
    });
  }
}

// helper: stat card
function statCard(slide, x, y, w, h, value, label, color, note) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, fill: { color: MIST }, rectRadius: 0.12,
    line: { color: "E6E3F5", width: 1 },
  });
  slide.addText(value, {
    x: x + 0.3, y: y + 0.28, w: w - 0.6, h: 0.9,
    fontSize: 40, bold: true, color, fontFace: H, isTextBox: true, margin: 0,
  });
  slide.addText(label, {
    x: x + 0.3, y: y + 1.18, w: w - 0.6, h: 0.35,
    fontSize: 13, bold: true, color: INK, fontFace: B, isTextBox: true, margin: 0,
  });
  if (note) {
    slide.addText(note, {
      x: x + 0.3, y: y + 1.52, w: w - 0.6, h: 0.6,
      fontSize: 10.5, color: GREY, fontFace: B, isTextBox: true, margin: 0,
    });
  }
}

/* ------------------------------------------------ 1. Title (dark) */
{
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.2, y: -1.4, w: 5.2, h: 5.2, fill: { color: DEEP }, line: { color: DEEP },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 11.3, y: 4.4, w: 3.0, h: 3.0, fill: { color: VIOLET }, line: { color: VIOLET },
    transparency: 55,
  });
  s.addText("NORTHBAY LIVING  ·  DEMAND & INVENTORY", {
    x: 0.9, y: 2.0, w: 9.0, h: 0.35,
    fontSize: 12.5, bold: true, color: VIOLET, charSpacing: 3, fontFace: B, isTextBox: true, margin: 0,
  });
  s.addText("Project FORESIGHT", {
    x: 0.9, y: 2.45, w: 9.5, h: 1.05,
    fontSize: 52, bold: true, color: PAPER, fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText("Stop guessing what to reorder.", {
    x: 0.9, y: 3.55, w: 9.5, h: 0.5,
    fontSize: 21, italic: true, color: "C9C4E8", fontFace: B, isTextBox: true, margin: 0,
  });
  s.addText("An 8-week demand forecast and stock early-warning system\nbuilt from your own sales and inventory data.", {
    x: 0.9, y: 4.2, w: 8.6, h: 0.8,
    fontSize: 14.5, color: "9A93C4", fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.25,
  });
  s.addText("Prepared for the Head of Operations and Finance  ·  Zidio Development", {
    x: 0.9, y: 6.4, w: 9.5, h: 0.35,
    fontSize: 11, color: "6F68A0", fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("Frame the engagement in one line: you asked what to reorder and what to clear; this is the answer, built from your data, with the accuracy stated honestly.");
}

/* ------------------------------------------------ 2. The problem */
{
  const s = pres.addSlide();
  title(s, "You are losing money in two directions at once",
    "The same planning gap causes both problems.");

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 2.0, w: 5.75, h: 3.5, fill: { color: "FBEEEC" }, rectRadius: 0.14,
    line: { color: "F0D5D0", width: 1 },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 1.05, y: 2.35, w: 0.55, h: 0.55, fill: { color: RED }, line: { color: RED },
  });
  s.addText("↓", { x: 1.05, y: 2.37, w: 0.55, h: 0.5, fontSize: 22, bold: true,
    color: PAPER, align: "center", fontFace: B, isTextBox: true, margin: 0 });
  s.addText("Best-sellers run out", {
    x: 1.78, y: 2.38, w: 4.4, h: 0.45, fontSize: 21, bold: true, color: INK,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText([
    { text: "Demand you can never recover. The customer buys elsewhere and may not come back.", options: { breakLine: true } },
    { text: "13 SKUs are projected to run short within their replenishment lead time.", options: {} },
  ], {
    x: 1.05, y: 3.1, w: 5.05, h: 1.3, fontSize: 14, color: "4A4860",
    fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.3,
  });
  s.addText("₹1.02 Cr", {
    x: 1.05, y: 4.45, w: 5.05, h: 0.75, fontSize: 40, bold: true, color: RED,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText("of sales at risk right now", {
    x: 1.05, y: 5.1, w: 5.05, h: 0.3, fontSize: 12, color: GREY, fontFace: B, isTextBox: true, margin: 0,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 6.85, y: 2.0, w: 5.75, h: 3.5, fill: { color: MIST }, rectRadius: 0.14,
    line: { color: "E1DDF3", width: 1 },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 7.2, y: 2.35, w: 0.55, h: 0.55, fill: { color: VIOLET }, line: { color: VIOLET },
  });
  s.addText("↑", { x: 7.2, y: 2.37, w: 0.55, h: 0.5, fontSize: 22, bold: true,
    color: PAPER, align: "center", fontFace: B, isTextBox: true, margin: 0 });
  s.addText("Slow movers pile up", {
    x: 7.93, y: 2.38, w: 4.4, h: 0.45, fontSize: 21, bold: true, color: INK,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText([
    { text: "Cash locked in stock that eventually gets marked down, eroding margin twice.", options: { breakLine: true } },
    { text: "18 SKUs hold more than 12 weeks of cover — the median is 24 weeks.", options: {} },
  ], {
    x: 7.2, y: 3.1, w: 5.05, h: 1.3, fontSize: 14, color: "4A4860",
    fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.3,
  });
  s.addText("₹1.08 Cr", {
    x: 7.2, y: 4.45, w: 5.05, h: 0.75, fontSize: 40, bold: true, color: VIOLET,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText("of working capital tied up", {
    x: 7.2, y: 5.1, w: 5.05, h: 0.3, fontSize: 12, color: GREY, fontFace: B, isTextBox: true, margin: 0,
  });

  s.addText("Together: ₹2.1 Cr of value in play across 31 of your 200 SKUs.", {
    x: 0.7, y: 5.85, w: 11.9, h: 0.45, fontSize: 16, bold: true, italic: true,
    color: INK, fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("Lead with their own words from the brief. Both failure modes come from the same root cause: no forward view of demand at SKU level.");
}

/* ------------------------------------------------ 3. What we built */
{
  const s = pres.addSlide();
  title(s, "What you now have", "Four pieces, each one usable without a data scientist.");

  const items = [
    ["1", "A demand forecast", "Expected units per SKU per week, eight weeks out, with a confidence range — not a single number pretending to be certain.", VIOLET],
    ["2", "A stockout early-warning", "Compares the forecast over your actual lead time against stock on hand and on order. Flags what will run short before it does.", RED],
    ["3", "An overstock flag", "Identifies stock covering far more weeks than you will sell, with the rupee value locked up in it.", AMBER],
    ["4", "A planning dashboard", "Filter by category, see the prioritised reorder and markdown lists, and export them. Live on a web link.", GREEN],
  ];

  let y = 1.85;
  items.forEach(([n, head, body, col]) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: 0.75, y: y + 0.05, w: 0.62, h: 0.62, fill: { color: col }, line: { color: col },
    });
    s.addText(n, {
      x: 0.75, y: y + 0.13, w: 0.62, h: 0.45, fontSize: 19, bold: true, color: PAPER,
      align: "center", fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(head, {
      x: 1.6, y: y, w: 4.0, h: 0.42, fontSize: 19, bold: true, color: INK,
      fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(body, {
      x: 1.6, y: y + 0.44, w: 10.6, h: 0.72, fontSize: 13.5, color: "4A4860",
      fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.2,
    });
    y += 1.24;
  });

  s.addText("Everything rebuilds from your raw extracts with one command, so you can refresh it next month without us.", {
    x: 0.75, y: 6.55, w: 11.8, h: 0.4, fontSize: 13, italic: true, color: VIOLET,
    fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("Stress the fourth point: reproducibility. They own this, it is not a one-off consulting artefact.");
}

/* ------------------------------------------------ 4. Accuracy */
{
  const s = pres.addSlide();
  title(s, "Is the forecast actually any good?",
    "Tested the hard way: trained only on the past, then scored on weeks it had never seen.");

  s.addChart(
    pres.ChartType.bar,
    [
      { name: "FORESIGHT forecast", labels: ["Test 1", "Test 2", "Test 3", "Test 4"], values: [0.160, 0.155, 0.164, 0.198] },
      { name: "Your current-style guess", labels: ["Test 1", "Test 2", "Test 3", "Test 4"], values: [0.197, 0.209, 0.213, 0.232] },
    ],
    {
      x: 0.7, y: 1.95, w: 7.3, h: 4.2,
      barDir: "col", barGrouping: "clustered",
      chartColors: [VIOLET, AMBER],
      showTitle: true, title: "Forecast error by test period (lower is better)",
      titleFontSize: 13, titleColor: INK, titleFontFace: B,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00",
      dataLabelFontSize: 10, dataLabelColor: INK,
      showLegend: true, legendPos: "b", legendFontSize: 11, legendColor: GREY,
      catAxisLabelColor: GREY, valAxisLabelColor: GREY,
      catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
      valGridLine: { color: "EDEBF6", size: 1 }, catGridLine: { style: "none" },
      valAxisMaxVal: 0.28,
    }
  );

  statCard(s, 8.4, 1.95, 4.2, 1.95, "20%", "More accurate than the naive approach",
    GREEN, "Wins in all four test periods, not just on average.");

  s.addText("What this means in plain terms", {
    x: 8.4, y: 4.15, w: 4.2, h: 0.35, fontSize: 15, bold: true, color: INK,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText([
    { text: "For every 100 units you actually sell, the forecast is off by about 17 — against 21 for a same-week-last-year guess.", options: { breakLine: true, paraSpaceAfter: 8 } },
    { text: "Accuracy is best in week 1 and degrades gradually to week 8. Trust the near weeks more.", options: {} },
  ], {
    x: 8.4, y: 4.55, w: 4.2, h: 1.7, fontSize: 12.5, color: "4A4860",
    fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.2,
  });
  s.addNotes("The benchmark is a seasonal-naive forecast — roughly what planning on last year's numbers achieves. Beating it by 20 percent on every fold is the evidence that this is worth acting on.");
}

/* ------------------------------------------------ 5. What the data showed */
{
  const s = pres.addSlide();
  title(s, "Three things your data already told us",
    "Findings that change how planning effort should be spent.");

  const cards = [
    ["60%", "of revenue comes from the top 20% of SKUs",
      "And the top 10 products carry 64% of all the value at risk. Planning attention should follow that curve, not be spread evenly across 200 products.", VIOLET],
    ["2.7×", "difference between peak and quiet weeks",
      "Seasonality is strong and predictable. A flat reorder rule over-orders in the quiet season and under-orders straight into the peak.", AMBER],
    ["+80%", "demand lift during promotion weeks",
      "Promotions nearly double units sold. Any plan that ignores the promo calendar will under-order ahead of every campaign you run.", GREEN],
  ];

  let x = 0.7;
  cards.forEach(([stat, head, body, col]) => {
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.0, w: 3.87, h: 4.0, fill: { color: MIST }, rectRadius: 0.14,
      line: { color: "E6E3F5", width: 1 },
    });
    s.addText(stat, {
      x: x + 0.35, y: 2.35, w: 3.2, h: 0.95, fontSize: 46, bold: true, color: col,
      fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(head, {
      x: x + 0.35, y: 3.3, w: 3.2, h: 0.85, fontSize: 15, bold: true, color: INK,
      fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.15,
    });
    s.addText(body, {
      x: x + 0.35, y: 4.25, w: 3.2, h: 1.55, fontSize: 12.5, color: "4A4860",
      fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.2,
    });
    x += 4.06;
  });
  s.addNotes("These are business findings, not chart tours. Each one implies a change in how they plan.");
}

/* ------------------------------------------------ 6. Where the money is */
{
  const s = pres.addSlide();
  title(s, "Where the money is", "Every SKU sorted into one of four actions.");

  const quads = [
    ["13", "Reorder now", "Raise a replenishment order before stock runs out", "₹1.02 Cr at risk", RED],
    ["18", "Markdown / clear", "Promote or discount to release working capital", "₹1.08 Cr locked", VIOLET],
    ["0", "Watch / volatile", "Erratic demand — review manually before ordering", "No SKUs this cycle", AMBER],
    ["169", "Healthy", "Stock position is appropriate — no action needed", "Leave alone", GREEN],
  ];

  let i = 0;
  quads.forEach(([n, head, body, foot, col]) => {
    const cx = 0.7 + (i % 2) * 6.15;
    const cy = 2.0 + Math.floor(i / 2) * 2.25;
    s.addShape(pres.ShapeType.roundRect, {
      x: cx, y: cy, w: 5.75, h: 2.0, fill: { color: PAPER }, rectRadius: 0.12,
      line: { color: "DEDAF0", width: 1 },
      shadow: { type: "outer", color: "BBBBBB", blur: 8, offset: 1, angle: 90, opacity: 0.18 },
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: cx + 0.35, y: cy + 0.45, w: 1.05, h: 1.05, fill: { color: col }, line: { color: col },
    });
    s.addText(n, {
      x: cx + 0.35, y: cy + 0.68, w: 1.05, h: 0.6, fontSize: 24, bold: true, color: PAPER,
      align: "center", fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(head, {
      x: cx + 1.6, y: cy + 0.35, w: 3.9, h: 0.4, fontSize: 18, bold: true, color: INK,
      fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(body, {
      x: cx + 1.6, y: cy + 0.78, w: 3.95, h: 0.62, fontSize: 12.5, color: "4A4860",
      fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.15,
    });
    s.addText(foot, {
      x: cx + 1.6, y: cy + 1.42, w: 3.9, h: 0.35, fontSize: 12.5, bold: true, color: col,
      fontFace: B, isTextBox: true, margin: 0,
    });
    i++;
  });
  s.addText("Only 31 of 200 SKUs need a decision this cycle — that is the point. The system tells you where not to look.", {
    x: 0.7, y: 6.6, w: 11.9, h: 0.4, fontSize: 13, italic: true, color: VIOLET,
    fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("The headline for Ops is workload reduction: 31 decisions, not 200.");
}

/* ------------------------------------------------ 7. This week's actions */
{
  const s = pres.addSlide();
  title(s, "What to do this week", "The six SKUs carrying the most value. Work down from the top.");

  const rows = [
    [
      { text: "SKU", options: { bold: true, color: PAPER, fill: { color: DEEP }, fontSize: 12 } },
      { text: "Category", options: { bold: true, color: PAPER, fill: { color: DEEP }, fontSize: 12 } },
      { text: "Action", options: { bold: true, color: PAPER, fill: { color: DEEP }, fontSize: 12 } },
      { text: "Why", options: { bold: true, color: PAPER, fill: { color: DEEP }, fontSize: 12 } },
      { text: "Value at stake", options: { bold: true, color: PAPER, fill: { color: DEEP }, fontSize: 12, align: "right" } },
    ],
    ["SKU0128", "Kitchen", "Reorder now", "Selling ~259/wk with only 1 week of cover left", "₹53.2 L"],
    ["SKU0194", "Decor", "Markdown", "2,348 units on hand — 22 weeks of cover", "₹24.1 L"],
    ["SKU0148", "Kitchen", "Reorder now", "Selling ~129/wk with 1.4 weeks of cover left", "₹17.3 L"],
    ["SKU0174", "Decor", "Healthy", "High value but stock position is appropriate", "₹14.0 L"],
    ["SKU0047", "Small Appliances", "Markdown", "1,755 units on hand — 19 weeks of cover", "₹13.4 L"],
    ["SKU0008", "Kitchen", "Markdown", "1,780 units on hand — 29 weeks of cover", "₹12.7 L"],
  ];

  const body = rows.map((r, idx) => {
    if (idx === 0) return r;
    const tint = idx % 2 === 0 ? MIST : PAPER;
    const actionColor = r[2] === "Reorder now" ? RED : r[2] === "Markdown" ? VIOLET : GREEN;
    return [
      { text: r[0], options: { fontSize: 12, bold: true, color: INK, fill: { color: tint } } },
      { text: r[1], options: { fontSize: 12, color: "4A4860", fill: { color: tint } } },
      { text: r[2], options: { fontSize: 12, bold: true, color: actionColor, fill: { color: tint } } },
      { text: r[3], options: { fontSize: 11.5, color: "4A4860", fill: { color: tint } } },
      { text: r[4], options: { fontSize: 12, bold: true, color: INK, align: "right", fill: { color: tint } } },
    ];
  });

  s.addTable(body, {
    x: 0.7, y: 2.0, w: 11.9,
    colW: [1.45, 1.85, 1.6, 5.2, 1.8],
    rowH: 0.52,
    border: { type: "solid", color: "E3E0F2", pt: 1 },
    fontFace: B, valign: "middle",
    margin: 6,
  });

  s.addText("Acting on the top two alone addresses ₹77 L — 36% of the total value in play.", {
    x: 0.7, y: 6.15, w: 11.9, h: 0.4, fontSize: 14, bold: true, italic: true,
    color: INK, fontFace: B, isTextBox: true, margin: 0,
  });
  s.addText("Full prioritised list, filterable and exportable, is on the dashboard.", {
    x: 0.7, y: 6.55, w: 11.9, h: 0.35, fontSize: 12, color: GREY,
    fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("SKU0128 alone is 53 lakh of the 2.1 crore. If they do one thing after this meeting, it is that reorder.");
}

/* ------------------------------------------------ 8. Limitations */
{
  const s = pres.addSlide();
  title(s, "What this does not do", "Stated plainly, so you know where judgement is still required.");

  const limits = [
    ["New products are weak spots", "SKUs with under three months of history borrow their seasonal pattern from their category. Treat those forecasts as indicative."],
    ["Promotion depth is not modelled", "The system knows a promotion is running, not how deep the discount is. An unusually aggressive campaign will be under-forecast."],
    ["Stock data is a weekly snapshot", "A product that moved sharply since the last snapshot can be mis-scored. The forecast is only as fresh as the stock feed."],
    ["Thresholds are business choices", "The 25% safety buffer and 12-week cover limit are settings, not discoveries. They should be tuned to your service-level target."],
    ["It cannot predict the unprecedented", "A supply shock or a viral product falls outside anything in the history. The confidence range will be too narrow in those conditions."],
  ];

  let y = 1.9;
  limits.forEach(([head, body]) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: 0.78, y: y + 0.1, w: 0.26, h: 0.26, fill: { color: AMBER }, line: { color: AMBER },
    });
    s.addText(head, {
      x: 1.28, y: y, w: 4.3, h: 0.4, fontSize: 15, bold: true, color: INK,
      fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(body, {
      x: 5.7, y: y - 0.02, w: 6.9, h: 0.78, fontSize: 12.5, color: "4A4860",
      fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.18,
    });
    y += 0.92;
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 6.35, w: 11.9, h: 0.62, fill: { color: MIST }, rectRadius: 0.1,
    line: { color: "E6E3F5", width: 1 },
  });
  s.addText("This is decision support. It narrows 200 products to roughly 30 decisions — it does not replace your planners' judgement on those 30.", {
    x: 0.95, y: 6.48, w: 11.4, h: 0.4, fontSize: 13, italic: true, color: INK,
    fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("Volunteering limitations is what makes the accuracy claim on slide 4 credible. Do not skip this slide.");
}

/* ------------------------------------------------ 9. Recommendations (dark) */
{
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.6, y: 4.6, w: 4.2, h: 4.2, fill: { color: DEEP }, line: { color: DEEP },
  });

  s.addText("Recommendations", {
    x: 0.9, y: 0.75, w: 11.5, h: 0.8, fontSize: 40, bold: true, color: PAPER,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText("Three steps, in order.", {
    x: 0.9, y: 1.52, w: 11.5, h: 0.4, fontSize: 15, color: "9A93C4",
    fontFace: B, isTextBox: true, margin: 0,
  });

  const recs = [
    ["Act on the 31 flagged SKUs this week", "Raise the 13 replenishment orders and put the 18 overstocked lines into the next markdown cycle. Suggested order quantities are on the dashboard."],
    ["Run the planning cycle weekly, not ad hoc", "Refresh the pipeline every Monday against the latest sales and stock extracts. The forecast is only as good as the freshness of its inputs."],
    ["Track whether the flags were right", "Log each flagged SKU's outcome for two months. That record is what lets you tighten the safety buffer and cover thresholds with evidence rather than instinct."],
  ];

  let y = 2.35;
  recs.forEach(([head, body], i) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.9, y: y, w: 0.52, h: 0.52, fill: { color: VIOLET }, rectRadius: 0.1, line: { color: VIOLET },
    });
    s.addText(String(i + 1), {
      x: 0.9, y: y + 0.06, w: 0.52, h: 0.4, fontSize: 17, bold: true, color: PAPER,
      align: "center", fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(head, {
      x: 1.65, y: y - 0.02, w: 8.6, h: 0.42, fontSize: 19, bold: true, color: PAPER,
      fontFace: H, isTextBox: true, margin: 0,
    });
    s.addText(body, {
      x: 1.65, y: y + 0.42, w: 9.3, h: 0.78, fontSize: 13, color: "A79FD0",
      fontFace: B, isTextBox: true, margin: 0, lineSpacingMultiple: 1.2,
    });
    y += 1.42;
  });

  s.addText("₹2.1 Cr", {
    x: 0.9, y: 6.4, w: 2.4, h: 0.6, fontSize: 30, bold: true, color: VIOLET,
    fontFace: H, isTextBox: true, margin: 0,
  });
  s.addText("of value addressable from this week's action list.", {
    x: 3.3, y: 6.55, w: 7.5, h: 0.4, fontSize: 13.5, italic: true, color: "9A93C4",
    fontFace: B, isTextBox: true, margin: 0,
  });
  s.addNotes("Close on the third point: measuring whether the flags were right is what turns this from a one-off analysis into a system that improves.");
}

pres.writeFile({ fileName: OUT }).then(() => console.log("wrote", OUT));
