import { Slot } from "@radix-ui/react-slot";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * 顶层导航容器。
 * 这里保留 shadcn/ui 风格的 Navigation Menu 语义，但不依赖额外的 Radix NavigationMenu 包，
 * 这样可以在当前项目依赖不变的前提下完成顶部菜单展示。
 */
function NavigationMenu({
  className,
  children,
  ...props
}: React.ComponentProps<"nav">) {
  return (
    <nav
      data-slot="navigation-menu"
      className={cn("relative flex items-center justify-start", className)}
      {...props}
    >
      {children}
    </nav>
  );
}

/**
 * 导航项列表。
 * 用列表结构承载顶部菜单，语义上更接近真实导航，也方便后续继续扩展菜单项。
 */
function NavigationMenuList({
  className,
  children,
  ...props
}: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="navigation-menu-list"
      className={cn("group flex list-none items-center justify-start gap-1", className)}
      {...props}
    >
      {children}
    </ul>
  );
}

/**
 * 单个导航项容器。
 * 单独包一层 list item，保持菜单项结构稳定，避免直接把按钮散落在导航列表里。
 */
function NavigationMenuItem({
  className,
  children,
  ...props
}: React.ComponentProps<"li">) {
  return (
    <li data-slot="navigation-menu-item" className={cn("relative", className)} {...props}>
      {children}
    </li>
  );
}

/**
 * 导航链接包装器。
 * 支持 asChild，这样外层可以继续复用 button 等已有基础组件，同时保留统一的导航语义封装。
 */
function NavigationMenuLink({
  className,
  asChild = false,
  children,
  ...props
}: React.ComponentProps<"a"> & {
  asChild?: boolean;
}) {
  const Comp = asChild ? Slot : "a";

  return (
    <Comp data-slot="navigation-menu-link" className={cn(className)} {...props}>
      {children}
    </Comp>
  );
}

export { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList };
