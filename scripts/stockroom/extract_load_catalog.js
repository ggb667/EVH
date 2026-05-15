const fs = require('fs');

const harPath = process.argv[2] || 'stockroom.instinctvet.com.only.lookup5.har';
const outPath = process.argv[3] || 'docs/stockroom-load-catalog.csv';

const text = fs.readFileSync(harPath, 'utf8');
const marker = 'live_fetch.response.load_catalog\\\",{\\\"error\\\":null,\\\"data\\\":\\\"';
const start = text.indexOf(marker);
if (start === -1) throw new Error('Could not find load_catalog payload');
const payloadStart = start + marker.length;
const payloadEnd = text.indexOf('\\\",\\\"request_id\\\"', payloadStart);
if (payloadEnd === -1) throw new Error('Could not find end of load_catalog payload');

const raw = text.slice(payloadStart, payloadEnd);
let decoded = raw;
for (let i = 0; i < 6; i += 1) {
  decoded = decoded
    .replace(/\\\\/g, '\\')
    .replace(/\\"/g, '"')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\r')
    .replace(/\\t/g, '\t');
}

const arrStart = decoded.indexOf('[{');
const arrEnd = decoded.lastIndexOf('}]');
if (arrStart === -1 || arrEnd === -1) throw new Error('Could not isolate global_products array');
const productsText = decoded.slice(arrStart + 1, arrEnd + 1);

const objects = [];
let depth = 0;
let inString = false;
let escaped = false;
let buffer = '';
for (const ch of productsText) {
  if (inString) {
    buffer += ch;
    if (escaped) {
      escaped = false;
    } else if (ch === '\\') {
      escaped = true;
    } else if (ch === '"') {
      inString = false;
    }
    continue;
  }

  if (ch === '"') {
    inString = true;
    buffer += ch;
    continue;
  }

  if (ch === '{') {
    depth += 1;
    buffer += ch;
    continue;
  }

  if (ch === '}') {
    depth -= 1;
    buffer += ch;
    if (depth === 0) {
      objects.push(buffer);
      buffer = '';
    }
    continue;
  }

  if (depth > 0) buffer += ch;
}

const pick = (obj, re) => {
  const m = obj.match(re);
  return m ? m[1] : '';
};

const csvEscape = value => {
  const s = String(value ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const rows = objects.map(obj => {
  const supplierIds = [...obj.matchAll(/"supplier_id":"([^"]+)"/g)].map(m => m[1]).join('|');
  const emrProductIds = [...obj.matchAll(/"emr_products":\[(.*?)\],"unit_ratio"/gs)]
    .flatMap(m => [...m[1].matchAll(/"id":"([a-f0-9-]{36})"/g)].map(x => x[1]))
    .join('|');

  return {
    code: pick(obj, /"code":"((?:\\.|[^"\\])*)"/),
    id: pick(obj, /"id":"((?:\\.|[^"\\])*)"/),
    label: pick(obj, /"label":"((?:\\.|[^"\\])*)"/),
    manufacturer_id: pick(obj, /"manufacturer":\{"id":"((?:\\.|[^"\\])*)"/),
    manufacturer_code: pick(obj, /"manufacturer":\{"id":"(?:\\.|[^"\\])*","code":"((?:\\.|[^"\\])*)"/),
    manufacturer_label: pick(obj, /"manufacturer":\{"id":"(?:\\.|[^"\\])*","code":"(?:\\.|[^"\\])*","label":"((?:\\.|[^"\\])*)"/),
    manufacturer_notes: pick(obj, /"manufacturer":\{"id":"(?:\\.|[^"\\])*","code":"(?:\\.|[^"\\])*","label":"(?:\\.|[^"\\])*","notes":"((?:\\.|[^"\\])*)"/),
    unit_cost: pick(obj, /"unit_cost":"((?:\\.|[^"\\])*)"/),
    buying_cost: pick(obj, /"buying_cost":"((?:\\.|[^"\\])*)"/),
    buying_unit_id: pick(obj, /"buying_unit":\{"id":"((?:\\.|[^"\\])*)"/),
    selling_unit_id: pick(obj, /"selling_unit":\{"id":"((?:\\.|[^"\\])*)"/),
    supplier_ids: supplierIds,
    emr_product_ids: emrProductIds,
  };
});

const header = [
  'code',
  'id',
  'label',
  'manufacturer_id',
  'manufacturer_code',
  'manufacturer_label',
  'manufacturer_notes',
  'unit_cost',
  'buying_cost',
  'buying_unit_id',
  'selling_unit_id',
  'supplier_ids',
  'emr_product_ids',
];

const csv = [header.join(',')]
  .concat(rows.map(row => header.map(key => csvEscape(row[key])).join(',')))
  .join('\n') + '\n';

fs.writeFileSync(outPath, csv);
console.log(`wrote ${rows.length} rows to ${outPath}`);
