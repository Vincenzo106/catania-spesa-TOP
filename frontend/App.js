import React, { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
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

const PRODUCTION_OFFERS_URL = "https://catania-spesa-top-backend.onrender.com/api/offers?limit=500";
const STORE_FILTER_ALL = "Tutti i supermercati";
const CATEGORY_FILTER_ALL = "Tutte le categorie";

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
  const [stores, setStores] = useState([STORE_FILTER_ALL]);
  const [categories, setCategories] = useState([CATEGORY_FILTER_ALL]);
  const [selectedStore, setSelectedStore] = useState(STORE_FILTER_ALL);
  const [selectedCategory, setSelectedCategory] = useState(CATEGORY_FILTER_ALL);
  const [shoppingList, setShoppingList] = useState({});
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const deferredSearch = useDeferredValue(search);
  const heroOpacity = useRef(new Animated.Value(0)).current;
  const heroTranslate = useRef(new Animated.Value(14)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(heroOpacity, {
        duration: 420,
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(heroTranslate, {
        duration: 420,
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [heroOpacity, heroTranslate]);

  useEffect(() => {
    loadOffers();
  }, []);

  async function loadOffers(isRefresh = false) {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError("");

    try {
      const response = await fetch(PRODUCTION_OFFERS_URL, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Server non disponibile (${response.status}).`);
      }

      const payload = await response.json();
      const items = Array.isArray(payload.items) ? payload.items : [];
      const availableStores = Array.isArray(payload.available_stores)
        ? payload.available_stores
        : [...new Set(items.map((offer) => offer.store))];
      const availableCategories = Array.isArray(payload.available_categories)
        ? payload.available_categories
        : [...new Set(items.map((offer) => offer.category))];

      startTransition(() => {
        setAllOffers(items);
        setStores([STORE_FILTER_ALL, ...availableStores]);
        setCategories([CATEGORY_FILTER_ALL, ...availableCategories]);
      });
    } catch (loadError) {
      setError(
        loadError.message ||
          "Impossibile caricare le offerte live. Controlla la connessione e riprova."
      );
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
        const matchesSearch = haystack.includes(normalizedSearch);
        return matchesStore && matchesCategory && matchesSearch;
      })
      .sort((left, right) => {
        if ((right.discount_percentage || 0) !== (left.discount_percentage || 0)) {
          return (right.discount_percentage || 0) - (left.discount_percentage || 0);
        }
        return left.product_name.localeCompare(right.product_name, "it");
      });
  }, [allOffers, deferredSearch, selectedCategory, selectedStore]);

  const bestDeals = useMemo(
    () =>
      [...visibleOffers]
        .sort((left, right) => (right.discount_percentage || 0) - (left.discount_percentage || 0))
        .slice(0, 6),
    [visibleOffers]
  );

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
            tintColor="#111827"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <Animated.View
          style={[
            styles.heroCard,
            {
              opacity: heroOpacity,
              transform: [{ translateY: heroTranslate }],
            },
          ]}
        >
          <View style={styles.heroHeaderRow}>
            <View style={styles.heroBadge}>
              <Text style={styles.heroBadgeText}>Dati live</Text>
            </View>
            <Text style={styles.heroSmallText}>Aggiornamento via internet</Text>
          </View>
          <Text style={styles.heroTitle}>
            Confronta le offerte dei supermercati di Catania ovunque ti trovi
          </Text>
          <Text style={styles.heroSubtitle}>
            L'app legge le offerte dal backend online e ti permette di filtrare, confrontare gli
            sconti e comporre la tua lista della spesa anche sotto rete 4G o 5G.
          </Text>
        </Animated.View>

        {loading ? (
          <View style={styles.loadingCard}>
            <ActivityIndicator size="large" color="#111827" />
            <Text style={styles.loadingTitle}>Caricamento offerte live</Text>
            <Text style={styles.loadingSubtitle}>
              Stiamo recuperando i dati aggiornati dal backend in produzione.
            </Text>
          </View>
        ) : null}

        {!loading ? (
          <>
            <View style={styles.statsRow}>
              <StatCard label="Offerte visibili" value={String(visibleOffers.length)} />
              <StatCard
                label="Miglior sconto"
                value={bestDiscount ? formatPercent(bestDiscount) : "N/D"}
              />
              <StatCard label="Totale carrello" value={formatPrice(shoppingTotal)} />
            </View>

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Filtra per supermercato"
                subtitle="Seleziona un'insegna specifica oppure confrontale tutte insieme."
              />
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {stores.map((store) => (
                  <FilterChip
                    key={store}
                    active={store === selectedStore}
                    label={getStoreLabel(store)}
                    onPress={() => {
                      startTransition(() => {
                        setSelectedStore(store);
                        setSelectedCategory(CATEGORY_FILTER_ALL);
                      });
                    }}
                  />
                ))}
              </ScrollView>
            </View>

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Filtra per categoria"
                subtitle="Passa rapidamente da frutta e verdura ai prodotti per la casa."
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

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Cerca prodotti"
                subtitle="Ricerca per nome, marca o categoria per trovare subito ciò che ti serve."
              />
              <TextInput
                onChangeText={setSearch}
                placeholder="Cerca prodotti, marche o categorie..."
                placeholderTextColor="#98A2B3"
                style={styles.searchInput}
                value={search}
              />
              {error ? <Text style={styles.errorText}>{error}</Text> : null}
            </View>

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Offerte top"
                subtitle="Selezione ordinata in base alla percentuale di sconto più alta."
              />
              {bestDeals.length > 0 ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {bestDeals.map((offer) => (
                    <BestDealCard
                      key={`best-${offer.id}`}
                      offer={offer}
                      formatPercent={formatPercent}
                      formatPrice={formatPrice}
                      onAdd={() => updateQuantity(offer, 1)}
                    />
                  ))}
                </ScrollView>
              ) : (
                <Text style={styles.helperText}>
                  Nessuna offerta top disponibile per i filtri selezionati.
                </Text>
              )}
            </View>

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Catalogo offerte"
                subtitle={`${visibleOffers.length} ${visibleOffers.length === 1 ? "articolo disponibile" : "articoli disponibili"} con i filtri attuali`}
              />
              {visibleOffers.map((offer) => (
                <OfferCard
                  key={offer.id}
                  offer={offer}
                  quantity={shoppingList[offer.id]?.quantity || 0}
                  formatPercent={formatPercent}
                  formatPrice={formatPrice}
                  onAdd={() => updateQuantity(offer, 1)}
                  onRemove={() => updateQuantity(offer, -1)}
                />
              ))}
              {visibleOffers.length === 0 ? (
                <Text style={styles.helperText}>Nessun articolo trovato con i filtri attuali.</Text>
              ) : null}
            </View>

            <ShoppingListPanel
              entries={shoppingEntries}
              formatPrice={formatPrice}
              itemCount={shoppingItemCount}
              total={shoppingTotal}
              onAdd={(offer) => updateQuantity(offer, 1)}
              onRemove={(offer) => updateQuantity(offer, -1)}
            />
          </>
        ) : null}

        {!loading && error ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorCardTitle}>Connessione al backend non riuscita</Text>
            <Text style={styles.errorCardText}>{error}</Text>
            <Pressable onPress={() => loadOffers()} style={styles.retryButton}>
              <Text style={styles.retryButtonText}>Riprova</Text>
            </Pressable>
          </View>
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
      <Text style={[styles.chipLabel, active ? styles.chipLabelActive : styles.chipLabelIdle]}>
        {label}
      </Text>
    </Pressable>
  );
}

function BestDealCard({ offer, formatPercent, formatPrice, onAdd }) {
  return (
    <View style={styles.bestCard}>
      <View style={styles.bestHeader}>
        <View style={styles.storeBadge}>
          <Text style={styles.storeBadgeText}>{offer.store}</Text>
        </View>
        <Text style={styles.discountText}>{formatPercent(offer.discount_percentage)}</Text>
      </View>
      <Text style={styles.bestTitle}>{offer.product_name}</Text>
      <Text style={styles.bestSubtitle}>{offer.brand || offer.categoryLabel || offer.category}</Text>
      <View style={styles.bestFooter}>
        <View>
          <Text style={styles.oldPrice}>{formatPrice(offer.original_price)}</Text>
          <Text style={styles.newPrice}>{formatPrice(offer.discounted_price)}</Text>
        </View>
        <Pressable onPress={onAdd} style={styles.primaryMiniButton}>
          <Text style={styles.primaryMiniButtonText}>Aggiungi</Text>
        </Pressable>
      </View>
    </View>
  );
}

function OfferCard({ offer, quantity, formatPercent, formatPrice, onAdd, onRemove }) {
  return (
    <View style={styles.offerCard}>
      <View style={styles.offerTopRow}>
        <View style={styles.storeBadge}>
          <Text style={styles.storeBadgeText}>{offer.store}</Text>
        </View>
        <Text style={styles.discountText}>{formatPercent(offer.discount_percentage)}</Text>
      </View>

      <Text style={styles.offerTitle}>{offer.product_name}</Text>
      <Text style={styles.offerSubtitle}>
        {offer.brand || "Marca non specificata"} - {offer.categoryLabel || offer.category}
      </Text>

      <View style={styles.offerMetaRow}>
        <View>
          <Text style={styles.oldPrice}>{formatPrice(offer.original_price)}</Text>
          <Text style={styles.newPrice}>{formatPrice(offer.discounted_price)}</Text>
        </View>
        <View style={styles.validityBlock}>
          <Text style={styles.validityLabel}>Valida fino al</Text>
          <Text style={styles.validityValue}>{offer.flyer_valid_until || "Non indicata"}</Text>
        </View>
      </View>

      <View style={styles.offerActionsRow}>
        <Pressable onPress={onAdd} style={styles.primaryButton}>
          <Text style={styles.primaryButtonText}>
            {quantity > 0 ? "Aggiungi ancora" : "Aggiungi"}
          </Text>
        </Pressable>
        <Pressable
          disabled={quantity === 0}
          onPress={onRemove}
          style={[styles.secondaryButton, quantity === 0 && styles.secondaryButtonDisabled]}
        >
          <Text
            style={[
              styles.secondaryButtonText,
              quantity === 0 && styles.secondaryButtonTextDisabled,
            ]}
          >
            {quantity > 0 ? `Rimuovi (${quantity})` : "Non presente"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function ShoppingListPanel({ entries, formatPrice, itemCount, total, onAdd, onRemove }) {
  return (
    <View style={styles.listCard}>
      <View style={styles.listHeader}>
        <View>
          <Text style={styles.listTitle}>Lista della spesa</Text>
          <Text style={styles.listCount}>
            {itemCount} {itemCount === 1 ? "articolo" : "articoli"}
          </Text>
        </View>
        <View>
          <Text style={styles.listTotalLabel}>Totale stimato</Text>
          <Text style={styles.listTotalValue}>{formatPrice(total)}</Text>
        </View>
      </View>

      {entries.length === 0 ? (
        <Text style={styles.emptyStateText}>
          Aggiungi un'offerta qui sopra per iniziare a comporre la tua spesa.
        </Text>
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
                <Text style={styles.stepperText}>-</Text>
              </Pressable>
              <Pressable onPress={() => onAdd(entry.offer)} style={styles.stepperButton}>
                <Text style={styles.stepperText}>+</Text>
              </Pressable>
            </View>
          </View>
        ))
      )}
    </View>
  );
}

function localizeOffer(offer) {
  return {
    ...offer,
    categoryLabel: getCategoryLabel(offer.category),
  };
}

function getStoreLabel(store) {
  return store === STORE_FILTER_ALL ? STORE_FILTER_ALL : store;
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

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Sconto n.d.";
  }

  return `${Math.round(Number(value))}% di sconto`;
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
    backgroundColor: "#F8F9FA",
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 32,
    paddingHorizontal: 20,
    paddingTop: 12,
  },
  heroCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    padding: 22,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 2,
  },
  heroHeaderRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
  },
  heroBadge: {
    backgroundColor: "#EEF2FF",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  heroBadgeText: {
    color: "#3730A3",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 12,
  },
  heroSmallText: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
  },
  heroTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 30,
    lineHeight: 38,
    marginBottom: 12,
  },
  heroSubtitle: {
    color: "#475467",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 15,
    lineHeight: 24,
  },
  loadingCard: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#EAECF0",
    marginTop: 16,
    padding: 28,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.04,
    shadowRadius: 12,
    elevation: 1,
  },
  loadingTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
    marginTop: 14,
  },
  loadingSubtitle: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
    marginTop: 8,
    textAlign: "center",
  },
  errorCard: {
    backgroundColor: "#FFF4ED",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#FDDCAB",
    marginTop: 16,
    padding: 18,
  },
  errorCardTitle: {
    color: "#9A3412",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 16,
    marginBottom: 6,
  },
  errorCardText: {
    color: "#9A3412",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
  },
  retryButton: {
    alignSelf: "flex-start",
    backgroundColor: "#111827",
    borderRadius: 12,
    marginTop: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  retryButtonText: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
  },
  statsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    marginTop: 16,
  },
  statCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#EAECF0",
    flexGrow: 1,
    minWidth: "30%",
    padding: 16,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.04,
    shadowRadius: 12,
    elevation: 1,
  },
  statValue: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 19,
  },
  statLabel: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    marginTop: 6,
  },
  sectionCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#EAECF0",
    marginTop: 16,
    padding: 18,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.04,
    shadowRadius: 12,
    elevation: 1,
  },
  sectionHeader: {
    marginBottom: 14,
  },
  sectionTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 20,
    marginBottom: 6,
  },
  sectionSubtitle: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    marginRight: 10,
    paddingHorizontal: 15,
    paddingVertical: 11,
  },
  chipActive: {
    backgroundColor: "#111827",
    borderColor: "#111827",
  },
  chipIdle: {
    backgroundColor: "#FFFFFF",
    borderColor: "#D0D5DD",
  },
  chipLabel: {
    fontSize: 13,
  },
  chipLabelActive: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
  },
  chipLabelIdle: {
    color: "#344054",
    fontFamily: "SpaceGrotesk-Regular",
  },
  searchInput: {
    backgroundColor: "#F8FAFC",
    borderColor: "#D0D5DD",
    borderRadius: 16,
    borderWidth: 1,
    color: "#101828",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 15,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  errorText: {
    color: "#B42318",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
    marginTop: 12,
  },
  helperText: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
    marginTop: 12,
  },
  bestCard: {
    backgroundColor: "#FFFFFF",
    borderColor: "#EAECF0",
    borderRadius: 16,
    borderWidth: 1,
    marginRight: 16,
    minHeight: 196,
    padding: 18,
    width: 270,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 12,
    elevation: 1,
  },
  bestHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  storeBadge: {
    backgroundColor: "#F2F4F7",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  storeBadgeText: {
    color: "#344054",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 12,
  },
  discountText: {
    color: "#027A48",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
  },
  bestTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 20,
    marginBottom: 6,
  },
  bestSubtitle: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    marginBottom: 20,
  },
  bestFooter: {
    alignItems: "flex-end",
    flex: 1,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  primaryMiniButton: {
    backgroundColor: "#111827",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  primaryMiniButtonText: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
  },
  offerCard: {
    backgroundColor: "#FFFFFF",
    borderColor: "#EAECF0",
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 16,
    padding: 18,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 12,
    elevation: 1,
  },
  offerTopRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  offerTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 21,
    marginBottom: 6,
  },
  offerSubtitle: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    marginBottom: 16,
  },
  offerMetaRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
  },
  validityBlock: {
    alignItems: "flex-end",
  },
  validityLabel: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
  },
  validityValue: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    marginTop: 4,
  },
  oldPrice: {
    color: "#98A2B3",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    textDecorationLine: "line-through",
  },
  newPrice: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 26,
    marginTop: 4,
  },
  offerActionsRow: {
    flexDirection: "row",
    gap: 10,
  },
  primaryButton: {
    backgroundColor: "#111827",
    borderRadius: 12,
    flex: 1,
    paddingVertical: 14,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    textAlign: "center",
  },
  secondaryButton: {
    backgroundColor: "#F8FAFC",
    borderColor: "#D0D5DD",
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    paddingVertical: 14,
  },
  secondaryButtonDisabled: {
    opacity: 0.45,
  },
  secondaryButtonText: {
    color: "#344054",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    textAlign: "center",
  },
  secondaryButtonTextDisabled: {
    color: "#98A2B3",
  },
  listCard: {
    backgroundColor: "#FFFFFF",
    borderColor: "#EAECF0",
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 16,
    padding: 18,
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 12,
    elevation: 1,
  },
  listHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
  },
  listTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
  listCount: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    marginTop: 6,
  },
  listTotalLabel: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    textAlign: "right",
  },
  listTotalValue: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 24,
    marginTop: 6,
    textAlign: "right",
  },
  emptyStateText: {
    color: "#667085",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
  },
  listRow: {
    alignItems: "center",
    borderTopColor: "#EAECF0",
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 14,
  },
  listRowContent: {
    flex: 1,
    paddingRight: 16,
  },
  listRowTitle: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 15,
  },
  listRowSubtitle: {
    color: "#667085",
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
    backgroundColor: "#F2F4F7",
    borderRadius: 12,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  stepperText: {
    color: "#101828",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
});
