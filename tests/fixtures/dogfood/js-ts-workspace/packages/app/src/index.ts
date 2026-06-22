import { describeValue } from "@dog/lib";
import { localName } from "./local";

export function render(): string {
  return describeValue(localName);
}
