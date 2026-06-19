import React from "react";
import { Pressable, StyleSheet, Text } from "react-native";

import { theme } from "../theme";

export default function FilterChip({ label, active, onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, active ? styles.chipActive : styles.chipIdle]}
    >
      <Text style={[styles.label, active ? styles.labelActive : styles.labelIdle]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: theme.radii.pill,
    borderWidth: 1,
    marginRight: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  chipActive: {
    backgroundColor: theme.colors.terracotta,
    borderColor: theme.colors.terracotta,
  },
  chipIdle: {
    backgroundColor: theme.colors.paper,
    borderColor: theme.colors.border,
  },
  label: {
    fontSize: 13,
  },
  labelActive: {
    color: theme.colors.white,
    fontFamily: "SpaceGrotesk-Bold",
  },
  labelIdle: {
    color: theme.colors.ink,
    fontFamily: "SpaceGrotesk-Regular",
  },
});
