const fs = require("fs");
const path = require("path");

const offersUtils = require(path.resolve(__dirname, "../src/utils/offers.shared.js"));

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function main() {
  const inputFile = process.argv[2];
  assert(inputFile, "Missing JSON payload path.");

  const offers = JSON.parse(fs.readFileSync(inputFile, "utf8"));
  assert(Array.isArray(offers), "Expected an array of offers.");
  assert(offers.length >= 3, "Expected at least three ingested offers.");

  const previewLines = offers.slice(0, 3).map(offersUtils.buildOfferPreview);
  const asciiPreviewLines = offers
    .slice(0, 3)
    .map((offer) => `${offer.product_name} - ${Number(offer.discounted_price).toFixed(2)} EUR`);
  assert(
    previewLines.every((line, index) =>
      line.includes(offersUtils.formatPrice(offers[index].discounted_price))
    ),
    "Expected each preview line to include the localized formatted discounted price."
  );

  const sampleEntries = [
    { offer: offers[0], quantity: 1 },
    { offer: offers[1], quantity: 2 },
  ];
  const total = offersUtils.computeShoppingListTotal(sampleEntries);
  assert(total > 0, "Shopping total should be positive.");
  assert(
    offersUtils.countShoppingItems(sampleEntries) === 3,
    "Shopping item count should match the summed quantities."
  );

  console.log("Frontend contract OK");
  console.log(asciiPreviewLines.join(" | "));
  console.log(`Sample shopping total: ${total.toFixed(2)} EUR`);
}

main();
