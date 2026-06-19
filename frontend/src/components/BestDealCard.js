import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";

import { theme } from "../theme";

export default function BestDealCard({ offer, formatPercent, formatPrice, onAdd }) {
  return (
    <LinearGradient colors={["#F7C65C", "#F7A449"]} style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.store}>{offer.store}</Text>
        <Text style={styles.discount}>{formatPercent(offer.discount_percentage)}</Text>
      </View>
      <Text style={styles.product}>{offer.product_name}</Text>
      <Text style={styles.brand}>{offer.brand || offer.category}</Text>
      <View style={styles.footer}>
        <View>
          <Text style={styles.oldPrice}>{formatPrice(offer.original_price)}</Text>
          <Text style={styles.newPrice}>{formatPrice(offer.discounted_price)}</Text>
        </View>
        <Pressable onPress={onAdd} style={styles.addButton}>
          <Text style={styles.addLabel}>Add</Text>
        </Pressable>
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: theme.radii.card,
    marginRight: 16,
    minHeight: 188,
    padding: 18,
    width: 270,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  store: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  discount: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 14,
  },
  product: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 20,
    marginBottom: 6,
  },
  brand: {
    color: theme.colors.mutedInk,
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    marginBottom: 20,
  },
  footer: {
    alignItems: "flex-end",
    flex: 1,
    flexDirection: "row",
    justifyContent: "space-between",
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
    fontSize: 24,
    marginTop: 4,
  },
  addButton: {
    backgroundColor: theme.colors.white,
    borderRadius: theme.radii.pill,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  addLabel: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 13,
  },
});
