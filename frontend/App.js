import AsyncStorage from "@react-native-async-storage/async-storage";
import React, {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
const METADATA_URL = `${API_BASE_URL}/metadata`;

const STORE_FILTER_ALL = "Tutti i supermercati";
const CATEGORY_FILTER_ALL = "Tutte le categorie";
const OFFERS_CACHE_KEY = "@catania-spesa-top/offers-cache-v1";
const FAVORITES_KEY = "@catania-spesa-top/favorites-v1";
const MAX_AUTO_RETRIES = 2;
const SLOW_SERVER_DELAY_MS = 5000;
const REQUEST_TIMEOUT_MS = 15000;

const STORE_ORDER = [
  "Coop",
  "Conad",
  "Dec\u00f2",
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
  const [favoriteKeys, setFavoriteKeys] = useState([]);
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorInfo, setErrorInfo] = useState(null);
  const [showWakeMessage, setShowWakeMessage] = useState(false);
  const [showingCachedOffers, setShowingCachedOffers] = useState(false);
  const [metadataText, setMetadataText] = useState(
    "Aggiornamento automatico periodico"
  );

  const deferredSearch = useDeferredValue(search);
  const loadingTimerRef = useRef(null);

  useEffect(() => {
    restoreFavorites();
    loadOffers();
    loadMetadata();

    return () => {
      clearLoadingTimer();
    };
  }, []);

  async function loadOffers(isRefresh = false) {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setErrorInfo(null);
    scheduleWakeMessage();

    try {
      const payload = await fetchOffersWithRetry();
      const items = Array.isArray(payload.items) ? payload.items : [];
      const availableStores = Array.isArray(payload.available_stores)
        ? payload.available_stores
        : [...new Set(items.map((offer) => offer.store).filter(Boolean))];
      const availableCategories = Array.isArray(payload.available_categories)
        ? payload.available_categories
        : [...new Set(items.map((offer) => offer.category).filter(Boolean))];

      applyOfferPayload(items, availableStores, availableCategories);
      setShowingCachedOffers(false);
      void loadMetadata();
      await saveOffersCache({
        items,
        availableStores,
        availableCategories,
        savedAt: new Date().toISOString(),
      });
    } catch (loadError) {
      const cachedPayload = await readOffersCache();

      if (cachedPayload?.items?.length) {
        applyOfferPayload(
          cachedPayload.items,
          cachedPayload.availableStores,
          cachedPayload.availableCategories
        );
        setShowingCachedOffers(true);
        setErrorInfo(null);
        void loadMetadata();
      } else {
        setErrorInfo({
          message: loadError.message || "Non riesco a raggiungere il server delle offerte.",
          status:
            typeof loadError.httpStatus === "number" ? String(loadError.httpStatus) : "N/D",
          url: loadError.requestUrl || OFFERS_URL,
        });
      }
    } finally {
      clearLoadingTimer();
      setLoading(false);
      setRefreshing(false);
    }
  }

  function applyOfferPayload(items, availableStores, availableCategories) {
    startTransition(() => {
      setAllOffers(Array.isArray(items) ? items : []);
      setStores([
        STORE_FILTER_ALL,
        ...sortStores([...(availableStores || []), ...STORE_ORDER]),
      ]);
      setCategories([
        CATEGORY_FILTER_ALL,
        ...sortCategories(availableCategories || []),
      ]);
    });
  }

  function updateQuantity(offer, delta) {
    const offerKey = makeOfferKey(offer);

    startTransition(() => {
      setShoppingList((current) => {
        const existing = current[offerKey];
        const nextQuantity = Math.max((existing?.quantity || 0) + delta, 0);

        if (nextQuantity === 0) {
          const { [offerKey]: _removed, ...rest } = current;
          return rest;
        }

        return {
          ...current,
          [offerKey]: {
            offer,
            quantity: nextQuantity,
          },
        };
      });
    });
  }

  async function restoreFavorites() {
    try {
      const rawValue = await AsyncStorage.getItem(FAVORITES_KEY);
      if (!rawValue) {
        return;
      }

      const parsed = JSON.parse(rawValue);
      if (Array.isArray(parsed)) {
        setFavoriteKeys(parsed.filter((item) => typeof item === "string"));
      }
    } catch {
      // Se il parsing fallisce ignoriamo i dati corrotti e continuiamo normalmente.
    }
  }

  async function loadMetadata() {
    try {
      const response = await fetchWithTimeout(
        METADATA_URL,
        {
          headers: {
            Accept: "application/json",
          },
        },
        8000
      );

      if (!response.ok) {
        throw new Error("Metadata non disponibili");
      }

      const payload = await response.json();
      setMetadataText(buildMetadataLabel(payload));
    } catch {
      setMetadataText("Aggiornamento automatico periodico");
    }
  }

  function toggleFavorite(offer) {
    const offerKey = makeOfferKey(offer);

    setFavoriteKeys((current) => {
      const next = current.includes(offerKey)
        ? current.filter((item) => item !== offerKey)
        : [...current, offerKey];

      void AsyncStorage.setItem(FAVORITES_KEY, JSON.stringify(next));
      return next;
    });
  }

  function scheduleWakeMessage() {
    clearLoadingTimer();
    setShowWakeMessage(false);
    loadingTimerRef.current = setTimeout(() => {
      setShowWakeMessage(true);
    }, SLOW_SERVER_DELAY_MS);
  }

  function clearLoadingTimer() {
    if (loadingTimerRef.current) {
      clearTimeout(loadingTimerRef.current);
      loadingTimerRef.current = null;
    }
    setShowWakeMessage(false);
  }

  const favoriteSet = useMemo(() => new Set(favoriteKeys), [favoriteKeys]);

  const visibleOffers = useMemo(() => {
    const normalizedSearch = deferredSearch.trim().toLowerCase();

    return allOffers
      .map(localizeOffer)
      .filter((offer) => {
        const matchesStore = selectedStore === STORE_FILTER_ALL || offer.store === selectedStore;
        const matchesCategory =
          selectedCategory === CATEGORY_FILTER_ALL || offer.category === selectedCategory;
        const matchesFavorite = !showFavoritesOnly || favoriteSet.has(makeOfferKey(offer));
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

        return matchesStore && matchesCategory && matchesFavorite && matchesSearch;
      })
      .sort((left, right) => {
        if ((right.discount_percentage || 0) !== (left.discount_percentage || 0)) {
          return (right.discount_percentage || 0) - (left.discount_percentage || 0);
        }
        return left.product_name.localeCompare(right.product_name, "it");
      });
  }, [
    allOffers,
    deferredSearch,
    favoriteSet,
    selectedCategory,
    selectedStore,
    showFavoritesOnly,
  ]);

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
  const comparisonSummary = useMemo(
    () => buildStoreComparison(shoppingEntries),
    [shoppingEntries]
  );
  const favoriteProductsVisible = visibleOffers.filter((offer) =>
    favoriteSet.has(makeOfferKey(offer))
  );

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
          <Text style={styles.metadataLabel}>{metadataText}</Text>
        </View>

        {showingCachedOffers ? (
          <NoticeCard
            title="Ultime offerte salvate"
            message="Stai visualizzando le ultime offerte disponibili. Prover\u00f2 ad aggiornare appena il server torna raggiungibile."
          />
        ) : null}

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

        <View style={styles.sectionCard}>
          <SectionHeader
            title="Preferiti"
            subtitle="Salva le offerte da tenere d'occhio e attiva il filtro dedicato quando vuoi concentrarti solo su quelle."
          />
          <View style={styles.preferenceRow}>
            <FilterChip
              active={showFavoritesOnly}
              label="Solo preferiti"
              onPress={() => {
                startTransition(() => setShowFavoritesOnly((current) => !current));
              }}
            />
            <Text style={styles.preferenceCount}>
              {favoriteKeys.length} {favoriteKeys.length === 1 ? "preferito" : "preferiti"}
            </Text>
          </View>
        </View>

        {loading ? (
          <View style={styles.feedbackCard}>
            <ActivityIndicator size="large" color="#2563EB" />
            <Text style={styles.feedbackTitle}>Caricamento offerte in corso...</Text>
            <Text style={styles.feedbackText}>Aggiorno le promozioni disponibili.</Text>
            {showWakeMessage ? (
              <Text style={styles.feedbackHint}>
                Il server delle offerte si sta avviando. Potrebbe volerci qualche secondo.
              </Text>
            ) : null}
          </View>
        ) : null}

        {!loading && errorInfo ? (
          <View style={styles.feedbackCard}>
            <Text style={styles.errorTitle}>Non riesco a raggiungere il server delle offerte</Text>
            <Text style={styles.feedbackText}>{errorInfo.message}</Text>
            <Text style={styles.feedbackHint}>
              Se \u00e8 il primo avvio, attendi qualche secondo e riprova.
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
                subtitle="Una selezione ordinata per sconto, utile per vedere subito le offerte pi\u00f9 interessanti."
              />
              {bestDeals.length > 0 ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {bestDeals.map((offer) => (
                    <BestDealCard
                      key={`best-${makeOfferKey(offer)}`}
                      isFavorite={favoriteSet.has(makeOfferKey(offer))}
                      offer={offer}
                      onAdd={() => updateQuantity(offer, 1)}
                      onToggleFavorite={() => toggleFavorite(offer)}
                    />
                  ))}
                </ScrollView>
              ) : showFavoritesOnly && favoriteKeys.length === 0 ? (
                <EmptyState
                  title="Nessun prodotto preferito"
                  message="Tocca il cuore sulle offerte per salvare i prodotti che ti interessano."
                />
              ) : (
                <EmptyState
                  title="Nessuna offerta trovata"
                  message="Nessuna offerta trovata con questi filtri."
                />
              )}
            </View>

            <View style={styles.sectionCard}>
              <SectionHeader
                title="Offerte disponibili"
                subtitle={`${visibleOffers.length} ${visibleOffers.length === 1 ? "prodotto trovato" : "prodotti trovati"} con i filtri attuali`}
              />
              {visibleOffers.length === 0 ? (
                showFavoritesOnly && favoriteKeys.length === 0 ? (
                  <EmptyState
                    title="Nessun prodotto preferito"
                    message="Aggiungi ai preferiti le offerte che vuoi ritrovare pi\u00f9 velocemente."
                  />
                ) : (
                  <EmptyState
                    title="Nessuna offerta trovata"
                    message="Nessuna offerta trovata con questi filtri."
                  />
                )
              ) : (
                visibleOffers.map((offer) => {
                  const offerKey = makeOfferKey(offer);
                  return (
                    <OfferCard
                      key={offerKey}
                      isFavorite={favoriteSet.has(offerKey)}
                      offer={offer}
                      quantity={shoppingList[offerKey]?.quantity || 0}
                      onAdd={() => updateQuantity(offer, 1)}
                      onRemove={() => updateQuantity(offer, -1)}
                      onToggleFavorite={() => toggleFavorite(offer)}
                    />
                  );
                })
              )}
            </View>

            <ShoppingListPanel
              entries={shoppingEntries}
              itemCount={shoppingItemCount}
              total={shoppingTotal}
              onAdd={(offer) => updateQuantity(offer, 1)}
              onRemove={(offer) => updateQuantity(offer, -1)}
            />

            <StoreComparisonPanel summary={comparisonSummary} />

            {showFavoritesOnly && favoriteProductsVisible.length > 0 ? (
              <View style={styles.sectionCard}>
                <SectionHeader
                  title="Preferiti"
                  subtitle="La tua selezione salvata resta disponibile anche quando chiudi e riapri l'app."
                />
                <Text style={styles.helperText}>
                  {favoriteProductsVisible.length}{" "}
                  {favoriteProductsVisible.length === 1
                    ? "prodotto preferito visibile"
                    : "prodotti preferiti visibili"}
                </Text>
              </View>
            ) : null}
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

function FavoriteButton({ active, onPress }) {
  return (
    <Pressable
      accessibilityLabel={active ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti"}
      onPress={onPress}
      style={[styles.favoriteButton, active && styles.favoriteButtonActive]}
    >
      <Text style={[styles.favoriteIcon, active && styles.favoriteIconActive]}>
        {active ? "\u2665" : "\u2661"}
      </Text>
    </Pressable>
  );
}

function BestDealCard({ offer, isFavorite, onAdd, onToggleFavorite }) {
  return (
    <View style={styles.bestDealCard}>
      <View style={styles.bestDealTop}>
        <Text style={styles.storePill}>{offer.store}</Text>
        <View style={styles.cardControls}>
          <Text style={styles.discountPill}>{formatPercentCompact(offer.discount_percentage)}</Text>
          <FavoriteButton active={isFavorite} onPress={onToggleFavorite} />
        </View>
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

function OfferCard({ offer, quantity, isFavorite, onAdd, onRemove, onToggleFavorite }) {
  return (
    <View style={styles.offerCard}>
      <View style={styles.offerHeader}>
        <Text style={styles.storePill}>{offer.store}</Text>
        <View style={styles.cardControls}>
          <Text style={styles.discountPill}>{formatPercentCompact(offer.discount_percentage)}</Text>
          <FavoriteButton active={isFavorite} onPress={onToggleFavorite} />
        </View>
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
        <EmptyState
          title="Lista vuota"
          message="Aggiungi qualche prodotto per stimare il totale della spesa."
        />
      ) : (
        entries.map((entry) => (
          <View key={makeOfferKey(entry.offer)} style={styles.listRow}>
            <View style={styles.listRowContent}>
              <Text style={styles.listRowTitle}>{entry.offer.product_name}</Text>
              <Text style={styles.listRowSubtitle}>
                {entry.quantity} x {formatPrice(entry.offer.discounted_price)} -{" "}
                {normalizeStoreLabel(entry.offer.store)}
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

function StoreComparisonPanel({ summary }) {
  return (
    <View style={styles.comparisonCard}>
      <SectionHeader
        title="Dove conviene?"
        subtitle="Confronto semplice dei prodotti presenti nella tua lista, raggruppati per supermercato."
      />

      {summary.canCompare ? (
        <>
          <View style={styles.comparisonHighlight}>
            <Text style={styles.comparisonLabel}>Pi\u00f9 conveniente</Text>
            <Text style={styles.comparisonValue}>{summary.cheapest.store}</Text>
            <Text style={styles.comparisonPrice}>
              Totale stimato: {formatPrice(summary.cheapest.total)}
            </Text>
            {summary.savings > 0 ? (
              <Text style={styles.comparisonHint}>
                Risparmio stimato: {formatPrice(summary.savings)} rispetto al pi\u00f9 caro
              </Text>
            ) : null}
          </View>

          {summary.rows.map((row) => (
            <View key={row.store} style={styles.comparisonRow}>
              <Text style={styles.comparisonRowStore}>{row.store}</Text>
              <Text style={styles.comparisonRowTotal}>{formatPrice(row.total)}</Text>
            </View>
          ))}
        </>
      ) : (
        <EmptyState
          title="Confronto non disponibile"
          message="Confronto disponibile quando pi\u00f9 supermercati hanno prodotti nella tua lista."
        />
      )}
    </View>
  );
}

function NoticeCard({ title, message }) {
  return (
    <View style={styles.noticeCard}>
      <Text style={styles.noticeTitle}>{title}</Text>
      <Text style={styles.noticeMessage}>{message}</Text>
    </View>
  );
}

function EmptyState({ title, message }) {
  return (
    <View style={styles.emptyStateCard}>
      <Text style={styles.emptyStateTitle}>{title}</Text>
      <Text style={styles.emptyStateText}>{message}</Text>
    </View>
  );
}

async function fetchOffersWithRetry(attempt = 0) {
  try {
    const response = await fetchWithTimeout(OFFERS_URL, {
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
        // Manteniamo il messaggio standard se il body non e' leggibile.
      }

      const httpError = new Error(serverMessage);
      httpError.httpStatus = response.status;
      httpError.requestUrl = OFFERS_URL;
      throw httpError;
    }

    return response.json();
  } catch (error) {
    if (attempt < MAX_AUTO_RETRIES) {
      await delay(1000 * (attempt + 1));
      return fetchOffersWithRetry(attempt + 1);
    }
    throw error;
  }
}

async function fetchWithTimeout(url, options, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      const timeoutError = new Error("Il server delle offerte non ha risposto in tempo.");
      timeoutError.requestUrl = url;
      throw timeoutError;
    }

    error.requestUrl = error.requestUrl || url;
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function saveOffersCache(payload) {
  try {
    await AsyncStorage.setItem(OFFERS_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Se il salvataggio locale fallisce continuiamo comunque con i dati live.
  }
}

async function readOffersCache() {
  try {
    const rawValue = await AsyncStorage.getItem(OFFERS_CACHE_KEY);
    if (!rawValue) {
      return null;
    }

    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed?.items) || parsed.items.length === 0) {
      return null;
    }

    return parsed;
  } catch {
    return null;
  }
}

function buildStoreComparison(entries) {
  const totalsByStore = new Map();

  entries.forEach((entry) => {
    const price = Number(entry.offer.discounted_price);
    const store = normalizeStoreLabel(entry.offer.store);

    if (!store || Number.isNaN(price)) {
      return;
    }

    const lineTotal = price * entry.quantity;
    totalsByStore.set(store, roundCurrency((totalsByStore.get(store) || 0) + lineTotal));
  });

  const rows = Array.from(totalsByStore.entries())
    .map(([store, total]) => ({
      store,
      total: roundCurrency(total),
    }))
    .sort((left, right) => left.total - right.total);

  if (rows.length < 2) {
    return {
      canCompare: false,
      rows,
    };
  }

  const cheapest = rows[0];
  const priciest = rows[rows.length - 1];

  return {
    canCompare: true,
    cheapest,
    priciest,
    rows,
    savings: roundCurrency(priciest.total - cheapest.total),
  };
}

function makeOfferKey(offer) {
  return [
    normalizeStoreLabel(offer.store),
    offer.product_name || "",
    offer.brand || "",
    String(offer.discounted_price ?? ""),
    offer.flyer_valid_until || "",
  ].join("::");
}

function localizeOffer(offer) {
  return {
    ...offer,
    store: normalizeStoreLabel(offer.store),
    categoryLabel: getCategoryLabel(offer.category),
  };
}

function normalizeStoreLabel(store) {
  const candidate = String(store || "").trim();
  const normalizedCandidate = normalizeForCompare(candidate);
  const matched = STORE_ORDER.find((item) => normalizeForCompare(item) === normalizedCandidate);
  return matched || candidate;
}

function normalizeForCompare(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function sortStores(inputStores) {
  return [...new Set(inputStores.map(normalizeStoreLabel).filter(Boolean))].sort((left, right) => {
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
  return [...new Set((inputCategories || []).filter(Boolean))].sort((left, right) =>
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

function buildMetadataLabel(metadata) {
  const lastSuccessfulUpdate = metadata?.last_successful_update;
  const lastAttemptedUpdate = metadata?.last_attempted_update || metadata?.last_check;
  const dataMode = metadata?.data_mode;

  if (lastSuccessfulUpdate) {
    const parsedDate = new Date(lastSuccessfulUpdate);
    if (!Number.isNaN(parsedDate.getTime())) {
      const now = new Date();
      const isSameDay =
        parsedDate.getDate() === now.getDate() &&
        parsedDate.getMonth() === now.getMonth() &&
        parsedDate.getFullYear() === now.getFullYear();

      if (isSameDay) {
        return `Volantini aggiornati automaticamente: oggi alle ${new Intl.DateTimeFormat("it-IT", {
          hour: "2-digit",
          minute: "2-digit",
        }).format(parsedDate)}`;
      }

      return `Ultimo aggiornamento automatico: ${new Intl.DateTimeFormat("it-IT", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }).format(parsedDate)}`;
    }
  }

  if (lastAttemptedUpdate) {
    const parsedCheck = new Date(lastAttemptedUpdate);
    if (!Number.isNaN(parsedCheck.getTime())) {
      const now = new Date();
      const isSameDay =
        parsedCheck.getDate() === now.getDate() &&
        parsedCheck.getMonth() === now.getMonth() &&
        parsedCheck.getFullYear() === now.getFullYear();

      if (isSameDay) {
        return `Ultimo controllo offerte: oggi alle ${new Intl.DateTimeFormat("it-IT", {
          hour: "2-digit",
          minute: "2-digit",
        }).format(parsedCheck)}`;
      }

      return `Ultimo controllo offerte: ${new Intl.DateTimeFormat("it-IT", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }).format(parsedCheck)}`;
    }
  }

  if (dataMode === "demo") {
    return "Catalogo demo disponibile, in attesa del primo aggiornamento automatico";
  }

  return "Aggiornamento automatico periodico";
}

function computeShoppingListTotal(entries) {
  return roundCurrency(
    entries.reduce(
      (sum, entry) => sum + Number(entry.offer.discounted_price || 0) * entry.quantity,
      0
    )
  );
}

function countShoppingItems(entries) {
  return entries.reduce((sum, entry) => sum + entry.quantity, 0);
}

function roundCurrency(value) {
  return Number(Number(value).toFixed(2));
}

function delay(durationMs) {
  return new Promise((resolve) => {
    setTimeout(resolve, durationMs);
  });
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
  metadataLabel: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 10,
  },
  noticeCard: {
    backgroundColor: "#EFF6FF",
    borderColor: "#BFDBFE",
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 16,
    padding: 16,
  },
  noticeTitle: {
    color: "#1D4ED8",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 15,
  },
  noticeMessage: {
    color: "#475467",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
    marginTop: 6,
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
  comparisonCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginTop: 16,
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
    marginTop: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
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
  preferenceRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  preferenceCount: {
    color: "#6B7280",
    flex: 1,
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    textAlign: "right",
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
    width: 286,
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginRight: 14,
    padding: 18,
  },
  bestDealTop: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 14,
  },
  cardControls: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  favoriteButton: {
    alignItems: "center",
    backgroundColor: "#F8FAFC",
    borderColor: "#D1D5DB",
    borderRadius: 999,
    borderWidth: 1,
    height: 34,
    justifyContent: "center",
    width: 34,
  },
  favoriteButtonActive: {
    backgroundColor: "#FEF2F2",
    borderColor: "#FECACA",
  },
  favoriteIcon: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 16,
    lineHeight: 18,
  },
  favoriteIconActive: {
    color: "#DC2626",
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
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
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
    alignItems: "flex-end",
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 20,
  },
  offerDetailsRow: {
    alignItems: "flex-end",
    flexDirection: "row",
    justifyContent: "space-between",
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
    alignItems: "center",
    borderTopColor: "#E5E7EB",
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
    backgroundColor: "#EFF6FF",
    borderRadius: 12,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  stepperButtonText: {
    color: "#1D4ED8",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
  comparisonHighlight: {
    backgroundColor: "#F8FAFC",
    borderColor: "#E5E7EB",
    borderRadius: 14,
    borderWidth: 1,
    marginBottom: 14,
    padding: 16,
  },
  comparisonLabel: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
  },
  comparisonValue: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 22,
    marginTop: 6,
  },
  comparisonPrice: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 16,
    marginTop: 8,
  },
  comparisonHint: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 8,
  },
  comparisonRow: {
    alignItems: "center",
    borderTopColor: "#E5E7EB",
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  comparisonRowStore: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
  },
  comparisonRowTotal: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
  },
  emptyStateCard: {
    backgroundColor: "#F8FAFC",
    borderColor: "#E5E7EB",
    borderRadius: 14,
    borderWidth: 1,
    padding: 16,
  },
  emptyStateTitle: {
    color: "#111827",
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 15,
  },
  emptyStateText: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
    marginTop: 6,
  },
  helperText: {
    color: "#6B7280",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    lineHeight: 20,
  },
});
