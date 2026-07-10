/// <reference types="vite/client" />

declare module "bun:test" {
  type Matcher = {
    toBe(value: unknown): void;
    toEqual(value: unknown): void;
    toBeNull(): void;
    toHaveLength(value: number): void;
    toMatchObject(value: unknown): void;
    [key: string]: (...args: unknown[]) => void;
  };

  export function describe(name: string, fn: () => void): void;
  export function beforeEach(fn: () => void): void;
  export function test(name: string, fn: () => void | Promise<void>): void;
  export function expect(value: unknown): Matcher;
}
