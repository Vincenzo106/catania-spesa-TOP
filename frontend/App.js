import React, { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import { SafeAreaView } from "react-native-safe-area-context";

const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL || "https://catania-spesa-top.onrender.com";
const OFFERS_URL = `${API_BASE_URL}/offers`;

const STORE_FILTER_ALL = "Tutti i supermercati";
const CATEGORY_FILTER_ALL = "Tutte le categorie";

const STORE_ORDER = [
  "Coop",
  "Conad",
  "Decò",
  "Famila",
  "MD",
  "Eurospin",
  "Lidl",
  "Spaccio Alimentare",
  "Crai",
];

const CATEGORY_LABELS = {
  [CATEGORY_FILTER_ALL]: "Tutte le categorie",
  Produce: "Frutta e verdura",
  Dairy: "Latticini",
  "Meat & Fish": "Carne e pesce",
  Pantry: "Dispensa",
  Frozen: "Surgelati",
  Drinks: "Bevande",
  Household: "Casa",
  Groceries: "Alimentari",
};

export default function App() {
  const [fontsLoaded] = useFonts({
    "SpaceGrotesk-Regular": require("./assets/fonts/SpaceGrotesk-Regular.ttf"),
    "SpaceGrotesk-Bold": require("./assets/fonts/SpaceGrotesk-Bold.ttf"),
  });

  const [allOffers, setAllOffers] = useState([]);
  const [stores, setStores] = useState([STORE_FILTER_ALL, ...STORE_ORDER]);
  const [categories, setCategories] = useState([CATEGORY_FILTER_ALL]);
  const [selectedStore, setSelectedStore] = useState(STORE_FILTER_ALL);
  const [selectedCategory, setSelectedCategory] = useState(CATEGORY_FILTER_ALL);
  const [shoppingList, setShoppingList] = useState({});
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorInfo, setErrorInfo] = useState(null);

  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    loadOffers();
  }, []);

  async function loadOffers(isRefresh = false) {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setErrorInfo(null);

    try {
      const response = await fetch(OFFERS_URL, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        let serverMessage = "Non riesco a raggiungere il server delle offerte.";

        try {
          const body = await response.json();
          serverMessage = body.detail || body.message || serverMessage;
        } catch {
          // Manteniamo il messaggio di fallback quando il body non e JSON.
        }

        const httpError = new Error(serverMessage);
        httpError.httpStatus = response.status;
        httpError.requestUrl = OFFERS_URL;
        throw httpError;
      }

      const payload = await response.json();
      const items = Array.isArray(payload.items) ? payload.items : [];
      const availableStores = Array.isArray(payload.available_stores)
        ? payload.available_stores
        : [...new Set(items.map((offer) => offer.store).filter(Boolean))];
      const availableCategories = Array.isArray(payload.available_categories)
        ? payload.available_categories
        : [...new Set(items.map((offer) => offer.category).filter(Boolean))];

      startTransition(() => {
        setAllOffers(items);
        setStores([STORE_FILTER_ALL, ...sortStores([...STORE_ORDER, ...availableStores])]);
        setCategories([CATEGORY_FILTER_ALL, ...sortCategories(availableCategories)]);
      });
    } catch (loadError) {
      setErrorInfo({
        message:
          loadError.message || "Non riesco a raggiungere il server delle offerte.",
        status: typeof loadError.httpStatus === "number" ? String(loadError.httpStatus) : "N/D",
        url: loadError.requestUrl || OFFERS_URL,
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  function updateQuantity(offer, delta) {
    startTransition(() => {
      setShoppingList((current) => {
        const existing = current[offer.id];
        const nextQuantity = Math.max((existing?.quantity || 0) + delta, 0);

        if (nextQuantity === 0) {
          const { [offer.id]: _removed, ...rest } = current;
          return rest;
        }

        return {
          ...current,
          [offer.id]: {
            offer,
            quantity: nextQuantity,
          },
        };
      });
    });
  }

  const visibleOffers = useMemo(() => {
    const normalizedSearch = deferredSearch.trim().toLowerCase();

    return allOffers
      .map(localizeOffer)
      .filter((offer) => {
        const matchesStore = selectedStore === STORE_FILTER_ALL || offer.store === selectedStore;
        const matchesCategory =
          selectedCategory === CATEGORY_FILTER_ALL || offer.category === selectedCategory;
        const haystack = [
          offer.product_name,
          offer.brand || "",
          offer.category,
          offer.categoryLabel,
          offer.store,
        ]
          .join(" ")
          .toLowerCase();

        return matchesStore && matchesCategory && haystack.includes(normalizedSearch);
      })
      .sort((left, right) => {
        if ((right.discount_percentage || 0) !== (left.discount_percentage || 0)) {
          return (right.discount_percentage || 0) - (left.discount_percentage || 0);
        }
        return left.product_name.localeCompare(right.product_name, "it");
      });
  }, [allOffers, deferredSearch, selectedCategory, selectedStore]);

  const bestDeals = useMemo(() => visibleOffers.slice(0, 5), [visibleOffers]);

  const shoppingEntries = useMemo(
    () =>
      Object.values(shoppingList).sort((left, right) =>
        left.offer.product_name.localeCompare(right.offer.product_name, "it")
      ),
    [shoppingList]
  );

  const shoppingTotal = computeShoppingListTotal(shoppingEntries);
  const shoppingItemCount = countShoppingItems(shoppingEntries);
  const bestDiscount = bestDeals[0]?.discount_percentage || null;

  if (!fontsLoaded) {
    return null;
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => loadOffers(true)}
            tintColor="#2563EB"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.headerBlock}>
          <View style={styles.headerBadge}>
            <Text style={styles.headerBadgeText}>Servizio online</Text>
          </View>
          <Text style={styles.appTitle}>Catania Spesa Top</Text>
          <Text style={styles.appSubtitle}>
            Trova le offerte migliori nei supermercati di Catania.
          </Text>
        </View>

        <View style={styles.statsRow}>
          <StatCard label="Offerte trovate" value={String(visibleOffers.length)} />
          <StatCard
            label="Miglior sconto"
            value={bestDiscount ? formatPercentCompact(bestDiscount) : "N/D"}
          />
          <StatCard label="Totale lista" value={formatPrice(shoppingTotal)} />
        </View>

        <View style={styles.searchCard}>
          <Text style={styles.sectionTitle}>Cerca prodotti</Text>
          <Text style={styles.sectionSubtitle}>
            Cerca per nome, marca o categoria per trovare rapidamente le promozioni utili.
          </Text>
          <TextInput
            onChangeText={setSearch}
            placeholder="Cerca prodotti..."
            placeholderTextColor="#9CA3AF"
            style={styles.searchInput}
            value={search}
          />
        </View>

        <View style={styles.sectionCard}>
          <SectionHeader
            title="Supermercati"
            subtitle="Seleziona un'insegna specifica oppure confronta tutte le offerte disponibili."
          />
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            {stores.map((store) => (
              <FilterChip
                key={store}
                active={store === selectedStore}
                label={store}
                onPress={() => {
                  startTransition(() => setSelectedStore(store));
                }}
              />
            ))}
          </ScrollView>
        </View>

        <View style={styles.sectionCard}>
          <SectionHeader
            title="Categorie"
            subtitle="Passa da alimentari, bevande e prodotti per la casa con un tocco."
          />
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            {categories.map((category) => (
              <FilterChip
                key={category}
                active={category === selectedCategory}
                label={getCategoryLabel(category)}
                onPress={() => {
                  startTransition(() => setSelectedCategory(category));
                }}
              />
            ))}
          </ScrollView>
        </View>

        {loading ? (
          <View style={styles.feedbackCard}>
            <ActivityIndicator size="large" color="#2563EB" />
            <Text style={styles.feedbackTitle}>Caricamento offerte in corso...</Text>
            <Text style={styles.feedbackText}>Aggiorno le promozioni disponibili.</Text>
            <Text style={styles.feedbackHint}>
              Se è il primo avvio, attendi qualche secondo e riprova.
            </Text>
          </View>
        ) : null}

        {!loading && errorInfo ? (
          <View style={styles.feedbackCard}>
            <Text style={styles.errorTitle}>Non riesco a raggiungere il server delle offerte</Text>
            <Text style={styles.feedbackText}>{errorInfo.message}</Text>
            <Text style={styles.feedbackHint}>
              Se è il primo avvio, attendi qualche secondo e riprova.
            </Text>
            <View style={styles.debugBox}>
              <Text style={styles.debugTitle}>Dettagli tecnici</Text>
              <Text style={styles.debugText}>Server chiamato: {errorInfo.url}</Text>
              <Text style={styles.debugText}>Stato HTTP: {errorInfo.status}</Text>
            </View>
            <Pressable onPress={() => loadOffers()} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Riprova</Text>
            </Pressable>
          </View>
        ) : null}

        {!loading && !errorInfo ? (
          <>
            <View style={styles.sectionCard}>
              <SectionHeader
                title="Migliori occasioni"
                subtitle="Una selezione ordinata per sconto, utile per vedere subito le offerte più interessanti."
              />
              {bestDeals.length > 0 ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {bestDeals.map((offer) => (
                    <BestDealCard
                      key={`best-${offer.id}`}
                      offer={offer}
                      onAdd={() => updateQuantity(offer, 1)}
                    />
                  ))}
                </ScrollView>
              ) : (
                <EmptyState text="Nessuna offerta trovata con questi filtri." />
              )}
            </View>

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Offerte disponibili"
                subtitle={`${visibleOffers.length} ${visibleOffers.length === 1 ? "prodotto trovato" : "prodotti trovati"} con i filtri attuali`}
              />
              {visibleOffers.length === 0 ? (
                <EmptyState text="Nessuna offerta trovata con questi filtri." />
              ) : (
                visibleOffers.map((offer) => (
                  <OfferCard
                    key={offer.id}
                    offer={offer}
                    quantity={shoppingList[offer.id]?.quantity || 0}
                    onAdd={() => updateQuantity(offer, 1)}
                    onRemove={() => updateQuantity(offer, -1)}
                  />
                ))
              )}
            </View>

            <ShoppingListPanel
              entries={shoppingEntries}
              itemCount={shoppingItemCount}
              total={shoppingTotal}
              onAdd={(offer) => updateQuantity(offer, 1)}
              onRemove={(offer) => updateQuantity(offer, -1)}
            />
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function StatCard({ label, value }) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function SectionHeader({ title, subtitle }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={styles.sectionSubtitle}>{subtitle}</Text>
    </View>
  );
}

function FilterChip({ label, active, onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, active ? styles.chipActive : styles.chipIdle]}
    >
      <Text style={[styles.chipText, active ? styles.chipTextActive : styles.chipTextIdle]}>
        {label}
      </Text>
    </Pressable>
  );
}

function BestDealCard({ offer, onAdd }) {
  return (
    <View style={styles.bestDealCard}>
      <View style={styles.bestDealTop}>
        <Text style={styles.storePill}>{offer.store}</Text>
        <Text style={styles.discountPill}>{formatPercentCompact(offer.discount_percentage)}</Text>
      </View>
      <Text style={styles.offerName}>{offer.product_name}</Text>
      <Text style={styles.offerMeta}>
        {offer.brand || "Marca non specificata"} - {offer.categoryLabel}
      </Text>
      <View style={styles.priceRow}>
        <View>
          <Text style={styles.oldPrice}>{formatPrice(offer.original_price)}</Text>
          <Text style={styles.newPrice}>{formatPrice(offer.discounted_price)}</Text>
        </View>
        <Pressable onPress={onAdd} style={styles.miniActionButton}>
          <Text style={styles.miniActionButtonText}>Aggiungi</Text>
        </Pressable>
      </View>
    </View>
  );
}

function OfferCard({ offer, quantity, onAdd, onRemove }) {
  return (
    <View style={styles.offerCard}>
      <View style={styles.offerHeader}>
        <Text style={styles.storePill}>{offer.store}</Text>
        <Text style={styles.discountPill}>{formatPercentCompact(offer.discount_percentage)}</Text>
      </View>
      <Text style={styles.offerName}>{offer.product_name}</Text>
      <Text style={styles.offerMeta}>
        {offer.brand || "Marca non specificata"} - {offer.categoryLabel}
      </Text>
      <View style={styles.offerDetailsRow}>
        <View>
          <Text style={styles.oldPrice}>{formatPrice(offer.original_price)}</Text>
          <Text style={styles.newPrice}>{formatPrice(offer.discounted_price)}</Text>
        </View>
        <View style={styles.validityBox}>
          <Text style={styles.validityLabel}>Valida fino al</Text>
          <Text style={styles.validityValue}>{formatDate(offer.flyer_valid_until)}</Text>
        </View>
      </View>
      <View style={styles.actionsRow}>
        <Pressable onPress={onAdd} style={styles.primaryButtonInline}>
          <Text style={styles.primaryButtonInlineText}>Aggiungi</Text>
        </Pressable>
        <Pressable
          disabled={quantity === 0}
          onPress={onRemove}
          style={[styles.secondaryButtonInline, quantity === 0 && styles.buttonDisabled]}
        >
          <Text
            style={[
              styles.secondaryButtonInlineText,
              quantity === 0 && styles.secondaryButtonInlineTextDisabled,
            ]}
          >
            {quantity > 0 ? `Rimuovi (${quantity})` : "Rimuovi"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function ShoppingListPanel({ entries, itemCount, total, onAdd, onRemove }) {
  return (
    <View style={styles.listCard}>
      <View style={styles.listHeader}>
        <View>
          <Text style={styles.listTitle}>Lista della spesa</Text>
          <Text style={styles.listSubtitle}>
            {itemCount} {itemCount === 1 ? "articolo selezionato" : "articoli selezionati"}
          </Text>
        </View>
        <View>
          <Text style={styles.listTotalLabel}>Totale lista</Text>
          <Text style={styles.listTotalValue}>{formatPrice(total)}</Text>
        </View>
      </View>
      {entries.length === 0 ? (
        <EmptyState text="Aggiungi qualche prodotto per stimare il totale della spesa." />
      ) : (
        entries.map((entry) => (
          <View key={entry.offer.id} style={styles.listRow}>
            <View style={styles.listRowContent}>
              <Text style={styles.listRowTitle}>{entry.offer.product_name}</Text>
              <Text style={styles.listRowSubtitle}>
                {entry.quantity} x {formatPrice(entry.offer.discounted_price)}
              </Text>
            </View>
            <View style={styles.stepperRow}>
              <Pressable onPress={() => onRemove(entry.offer)} style={styles.stepperButton}>
                <Text style={styles.stepperButtonText}>-</Text>
              </Pressable>
              <Pressable onPress={() => onAdd(entry.offer)} style={styles.stepperButton}>
                <Text style={styles.stepperButtonText}>+</Text>
              </Pressable>
            </View>
          </View>
        ))
      )}
    </View>
  );
}

function EmptyState({ text }) {
  return <Text style={styles.emptyStateText}>{text}</Text>;
}

function localizeOffer(offer) {
  return {
    ...offer,
    store: normalizeStoreLabel(offer.store),
    categoryLabel: getCategoryLabel(offer.category),
  };
}

function normalizeStoreLabel(store) {
  const normalized = String(store || "").trim().toLowerCase();
  const matched = STORE_ORDER.find((item) => item.toLowerCase() === normalized);
  return matched || store;
}

function sortStores(inputStores) {
  return [...new Set(inputStores.map(normalizeStoreLabel))].sort((left, right) => {
    const leftIndex = STORE_ORDER.indexOf(left);
    const rightIndex = STORE_ORDER.indexOf(right);

    if (leftIndex === -1 && rightIndex === -1) {
      return left.localeCompare(right, "it");
    }
    if (leftIndex === -1) {
      return 1;
    }
    if (rightIndex === -1) {
      return -1;
    }
    return leftIndex - rightIndex;
  });
}

function sortCategories(inputCategories) {
  return [...new Set(inputCategories)].sort((left, right) =>
    getCategoryLabel(left).localeCompare(getCategoryLabel(right), "it")
  );
}

function getCategoryLabel(category) {
  return CATEGORY_LABELS[category] || category;
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/D";
  }

  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  }).format(Number(value));
}

function formatPercentCompact(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Sconto N/D";
  }
  return `-${Math.round(Number(value))}%`;
}

function formatDate(value) {
  if (!value) {
    return "Non indicata";
  }

  try {
    return new Intl.DateTimeFormat("it-IT", {
      day: "2-digit",
      month: "short",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
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

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#F6F7FB",
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 28,
  },
  headerBlock: {
    marginBottom: 18,
  },
  headerBadge: {
    alignSelf: "flex-start",
    backgroundColor: "#E0ECFF",
    borderRadius: 999,
    marginBottom: 12,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  headerBadgeText: {
    color: "#1D4ED8",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 12,
  },
  appTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 30,
    lineHeight: 36,
  },
  appSubtitle: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 15,
    lineHeight: 24,
    marginTop: 8,
  },
  statsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    marginBottom: 16,
  },
  statCard: {
    flexGrow: 1,
    minWidth: "30%",
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    padding: 16,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 18,
    elevation: 1,
  },
  statValue: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 20,
  },
  statLabel: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    marginTop: 6,
  },
  searchCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginBottom: 16,
    padding: 18,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 18,
    elevation: 1,
  },
  sectionCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginBottom: 16,
    padding: 18,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 18,
    elevation: 1,
  },
  sectionHeader: {
    marginBottom: 14,
  },
  sectionTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 19,
    marginBottom: 6,
  },
  sectionSubtitle: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
  },
  searchInput: {
    backgroundColor: "#F8FAFC",
    borderColor: "#D1D5DB",
    borderRadius: 14,
    borderWidth: 1,
    color: "#111827",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 15,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginTop: 14,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    marginRight: 10,
    paddingHorizontal: 15,
    paddingVertical: 10,
  },
  chipActive: {
    backgroundColor: "#2563EB",
    borderColor: "#2563EB",
  },
  chipIdle: {
    backgroundColor: "#F8FAFC",
    borderColor: "#D1D5DB",
  },
  chipText: {
    fontSize: 13,
  },
  chipTextActive: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
  },
  chipTextIdle: {
    color: "#374151",
    fontFamily: "SpaceGrotesk-Regular",
  },
  feedbackCard: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginBottom: 16,
    padding: 24,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 18,
    elevation: 1,
  },
  feedbackTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
    marginTop: 14,
    textAlign: "center",
  },
  errorTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
    textAlign: "center",
  },
  feedbackText: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
    marginTop: 10,
    textAlign: "center",
  },
  feedbackHint: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 8,
    textAlign: "center",
  },
  debugBox: {
    width: "100%",
    backgroundColor: "#F8FAFC",
    borderColor: "#E5E7EB",
    borderRadius: 14,
    borderWidth: 1,
    marginTop: 16,
    padding: 14,
  },
  debugTitle: {
    color: "#374151",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
    marginBottom: 6,
  },
  debugText: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    lineHeight: 18,
  },
  primaryButton: {
    backgroundColor: "#2563EB",
    borderRadius: 14,
    marginTop: 18,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
  },
  bestDealCard: {
    width: 278,
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginRight: 14,
    padding: 18,
  },
  bestDealTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 14,
  },
  storePill: {
    alignSelf: "flex-start",
    backgroundColor: "#EEF2FF",
    borderRadius: 999,
    color: "#1E3A8A",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 12,
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  discountPill: {
    color: "#DC2626",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
  },
  offerCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginBottom: 14,
    padding: 18,
  },
  offerHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  offerName: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 21,
    lineHeight: 28,
  },
  offerMeta: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 6,
  },
  priceRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
    marginTop: 20,
  },
  offerDetailsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
    marginTop: 18,
  },
  oldPrice: {
    color: "#9CA3AF",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    textDecorationLine: "line-through",
  },
  newPrice: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 28,
    marginTop: 4,
  },
  validityBox: {
    alignItems: "flex-end",
  },
  validityLabel: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
  },
  validityValue: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    marginTop: 4,
  },
  actionsRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 18,
  },
  primaryButtonInline: {
    flex: 1,
    backgroundColor: "#2563EB",
    borderRadius: 14,
    paddingVertical: 14,
  },
  primaryButtonInlineText: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    textAlign: "center",
  },
  secondaryButtonInline: {
    flex: 1,
    backgroundColor: "#F8FAFC",
    borderColor: "#D1D5DB",
    borderRadius: 14,
    borderWidth: 1,
    paddingVertical: 14,
  },
  secondaryButtonInlineText: {
    color: "#374151",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    textAlign: "center",
  },
  secondaryButtonInlineTextDisabled: {
    color: "#9CA3AF",
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  miniActionButton: {
    backgroundColor: "#0F766E",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  miniActionButtonText: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
  },
  listCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    padding: 18,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 18,
    elevation: 1,
  },
  listHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 16,
  },
  listTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
  listSubtitle: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    marginTop: 6,
  },
  listTotalLabel: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    textAlign: "right",
  },
  listTotalValue: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 24,
    marginTop: 6,
    textAlign: "right",
  },
  listRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderTopWidth: 1,
    borderTopColor: "#E5E7EB",
    paddingVertical: 14,
  },
  listRowContent: {
    flex: 1,
    paddingRight: 16,
  },
  listRowTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 15,
  },
  listRowSubtitle: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    marginTop: 4,
  },
  stepperRow: {
    flexDirection: "row",
    gap: 8,
  },
  stepperButton: {
    alignItems: "center",
    justifyContent: "center",
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: "#EFF6FF",
  },
  stepperButtonText: {
    color: "#1D4ED8",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
  emptyStateText: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
  },
});
