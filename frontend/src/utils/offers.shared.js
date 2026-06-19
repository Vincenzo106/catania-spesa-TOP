function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }

  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "No %";
  }
  return `${Math.round(Number(value))}% off`;
}

function computeShoppingListTotal(entries) {
  return Number(
    entries
      .reduce((sum, entry) => sum + Number(entry.offer.discounted_price || 0) * entry.quantity, 0)
      .toFixed(2)
  );
}

function countShoppingItems(entries) {
  return entries.reduce((sum, entry) => sum + entry.quantity, 0);
}

function buildOfferPreview(offer) {
  return `${offer.product_name} — ${formatPrice(offer.discounted_price)}`;
}

module.exports = {
  buildOfferPreview,
  computeShoppingListTotal,
  countShoppingItems,
  formatPercent,
  formatPrice,
};
