import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";

import { theme } from "../theme";

export default function ShoppingListPanel({
  entries,
  formatPrice,
  itemCount,
  total,
  onAdd,
  onRemove,
}) {
  return (
    <LinearGradient colors={["#1E1B18", "#31271F"]} style={styles.panel}>
      <View style={styles.header}>
        <View>
          <Text style={styles.headerLabel}>Personal Shopping List</Text>
          <Text style={styles.headerCount}>
            {itemCount} item{itemCount === 1 ? "" : "s"}
          </Text>
        </View>
        <View>
          <Text style={styles.totalLabel}>Estimated total</Text>
          <Text style={styles.totalValue}>{formatPrice(total)}</Text>
        </View>
      </View>

      {entries.length === 0 ? (
        <Text style={styles.emptyState}>
          Tap any offer above to start building your weekly grocery basket.
        </Text>
      ) : (
        entries.map((entry) => (
          <View key={entry.offer.id} style={styles.row}>
            <View style={styles.rowContent}>
              <Text style={styles.rowTitle}>{entry.offer.product_name}</Text>
              <Text style={styles.rowSubtitle}>
                {entry.quantity} × {formatPrice(entry.offer.discounted_price)}
              </Text>
            </View>
            <View style={styles.rowActions}>
              <Pressable onPress={() => onRemove(entry.offer)} style={styles.stepperButton}>
                <Text style={styles.stepperLabel}>-</Text>
              </Pressable>
              <Pressable onPress={() => onAdd(entry.offer)} style={styles.stepperButton}>
                <Text style={styles.stepperLabel}>+</Text>
              </Pressable>
            </View>
          </View>
        ))
      )}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: 30,
    marginBottom: 30,
    marginTop: 10,
    padding: 20,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 18,
  },
  headerLabel: {
    color: theme.colors.white,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
  headerCount: {
    color: "#E0D6C9",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    marginTop: 6,
  },
  totalLabel: {
    color: "#E0D6C9",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 12,
    textAlign: "right",
  },
  totalValue: {
    color: theme.colors.citrus,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 24,
    marginTop: 6,
    textAlign: "right",
  },
  emptyState: {
    color: "#E0D6C9",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 14,
    lineHeight: 22,
  },
  row: {
    alignItems: "center",
    borderTopColor: "rgba(255,255,255,0.1)",
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 14,
  },
  rowContent: {
    flex: 1,
    paddingRight: 16,
  },
  rowTitle: {
    color: theme.colors.white,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 15,
  },
  rowSubtitle: {
    color: "#E0D6C9",
    fontFamily: "SpaceGrotesk-Regular",
    fontSize: 13,
    marginTop: 4,
  },
  rowActions: {
    flexDirection: "row",
    gap: 8,
  },
  stepperButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.12)",
    borderRadius: theme.radii.pill,
    height: 38,
    justifyContent: "center",
    width: 38,
  },
  stepperLabel: {
    color: theme.colors.white,
    fontFamily: "SpaceGrotesk-Bold",
    fontSize: 18,
  },
});
