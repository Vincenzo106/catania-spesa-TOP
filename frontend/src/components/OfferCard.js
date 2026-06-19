import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "../theme";

export default function OfferCard({
  offer,
  quantity,
  formatPercent,
  formatPrice,
  onAdd,
  onRemove,
}) {
  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{offer.store}</Text>
        </View>
        <Text style={styles.discountText}>{formatPercent(offer.discount_percentage)}</Text>
      </View>

      <Text style={styles.title}>{offer.product_name}</Text>
      <Text style={styles.subtitle}>
        {offer.brand || "Marca non indicata"} • {offer.category}
      </Text>

      <View style={styles.metaRow}>
        <View>
          <Text style={styles.oldPrice}>{formatPrice(offer.original_price)}</Text>
          <Text style={styles.newPrice}>{formatPrice(offer.discounted_price)}</Text>
        </View>
        <View style={styles.validityBlock}>
          <Text style={styles.validityLabel}>Valid until</Text>
          <Text style={styles.validityValue}>{offer.flyer_valid_until || "N/A"}</Text>
        </View>
      </View>

      <View style={styles.actionsRow}>
        <Pressable onPress={onAdd} style={styles.primaryButton}>
          <Text style={styles.primaryButtonLabel}>{quantity > 0 ? "Add one more" : "Add to list"}</Text>
        </Pressable>
        <Pressable
          disabled={quantity === 0}
          onPress={onRemove}
          style={[styles.secondaryButton, quantity === 0 && styles.secondaryButtonDisabled]}
        >
          <Text
            style={[
              styles.secondaryButtonLabel,
              quantity === 0 && styles.secondaryButtonLabelDisabled,
            ]}
          >
            {quantity > 0 ? `Remove (${quantity})` : "Not added"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.paper,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.card,
    borderWidth: 1,
    marginBottom: 16,
    padding: 18,
    shadowColor: theme.colors.cardShadow,
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 1,
    shadowRadius: 24,
  },
  topRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  badge: {
    backgroundColor: theme.colors.sage,
    borderRadius: theme.radii.pill,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  badgeText: {
    color: theme.colors.olive,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 12,
    letterSpacing: 0.4,
    textTransform: "uppercase",
  },
  discountText: {
    color: theme.colors.success,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
  },
  title: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 21,
    marginBottom: 6,
  },
  subtitle: {
    color: theme.colors.mutedInk,
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    marginBottom: 16,
  },
  metaRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
  },
  oldPrice: {
    color: theme.colors.mutedInk,
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    textDecorationLine: "line-through",
  },
  newPrice: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 26,
    marginTop: 4,
  },
  validityBlock: {
    alignItems: "flex-end",
  },
  validityLabel: {
    color: theme.colors.mutedInk,
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
  },
  validityValue: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    marginTop: 4,
  },
  actionsRow: {
    flexDirection: "row",
    gap: 10,
  },
  primaryButton: {
    backgroundColor: theme.colors.terracotta,
    borderRadius: theme.radii.pill,
    flex: 1,
    paddingVertical: 14,
  },
  primaryButtonLabel: {
    color: theme.colors.white,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    textAlign: "center",
  },
  secondaryButton: {
    backgroundColor: theme.colors.white,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.pill,
    borderWidth: 1,
    flex: 1,
    paddingVertical: 14,
  },
  secondaryButtonDisabled: {
    opacity: 0.45,
  },
  secondaryButtonLabel: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
    textAlign: "center",
  },
  secondaryButtonLabelDisabled: {
    color: theme.colors.mutedInk,
  },
});
