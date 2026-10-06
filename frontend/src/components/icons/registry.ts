// Icon registry (DESIGN_SYSTEM DS-ICO-01 to DS-ICO-08): the only importer of @phosphor-icons/react.
// It re-exports exactly the DS-ICO-07 icons and the DS-CMP-02 navigation icons under their Phosphor
// core names; components import from here, never from the package (DS-LINT-07). Deep imports keep
// the bundle to the icons listed. The `Sparkle` export is imported only by components/ai.
import { ArrowSquareOutIcon } from "@phosphor-icons/react/dist/csr/ArrowSquareOut";
import { ArrowsClockwiseIcon } from "@phosphor-icons/react/dist/csr/ArrowsClockwise";
import { ArrowUUpLeftIcon } from "@phosphor-icons/react/dist/csr/ArrowUUpLeft";
import { BellIcon } from "@phosphor-icons/react/dist/csr/Bell";
import { BooksIcon } from "@phosphor-icons/react/dist/csr/Books";
import { BuildingsIcon } from "@phosphor-icons/react/dist/csr/Buildings";
import { CalendarBlankIcon } from "@phosphor-icons/react/dist/csr/CalendarBlank";
import { CalendarDotsIcon } from "@phosphor-icons/react/dist/csr/CalendarDots";
import { CaretDownIcon } from "@phosphor-icons/react/dist/csr/CaretDown";
import { CaretLeftIcon } from "@phosphor-icons/react/dist/csr/CaretLeft";
import { CaretRightIcon } from "@phosphor-icons/react/dist/csr/CaretRight";
import { CaretUpIcon } from "@phosphor-icons/react/dist/csr/CaretUp";
import { ChartBarIcon } from "@phosphor-icons/react/dist/csr/ChartBar";
import { ChatTextIcon } from "@phosphor-icons/react/dist/csr/ChatText";
import { CheckCircleIcon } from "@phosphor-icons/react/dist/csr/CheckCircle";
import { CircleIcon } from "@phosphor-icons/react/dist/csr/Circle";
import { CircleDashedIcon } from "@phosphor-icons/react/dist/csr/CircleDashed";
import { CircleHalfIcon } from "@phosphor-icons/react/dist/csr/CircleHalf";
import { ClockCounterClockwiseIcon } from "@phosphor-icons/react/dist/csr/ClockCounterClockwise";
import { ColumnsIcon } from "@phosphor-icons/react/dist/csr/Columns";
import { CommandIcon } from "@phosphor-icons/react/dist/csr/Command";
import { CopySimpleIcon } from "@phosphor-icons/react/dist/csr/CopySimple";
import { DatabaseIcon } from "@phosphor-icons/react/dist/csr/Database";
import { DotsThreeIcon } from "@phosphor-icons/react/dist/csr/DotsThree";
import { DownloadSimpleIcon } from "@phosphor-icons/react/dist/csr/DownloadSimple";
import { EqualsIcon } from "@phosphor-icons/react/dist/csr/Equals";
import { FileTextIcon } from "@phosphor-icons/react/dist/csr/FileText";
import { FunctionIcon } from "@phosphor-icons/react/dist/csr/Function";
import { FunnelIcon } from "@phosphor-icons/react/dist/csr/Funnel";
import { GearSixIcon } from "@phosphor-icons/react/dist/csr/GearSix";
import { HourglassMediumIcon } from "@phosphor-icons/react/dist/csr/HourglassMedium";
import { HouseIcon } from "@phosphor-icons/react/dist/csr/House";
import { InfoIcon } from "@phosphor-icons/react/dist/csr/Info";
import { KeyboardIcon } from "@phosphor-icons/react/dist/csr/Keyboard";
import { ListChecksIcon } from "@phosphor-icons/react/dist/csr/ListChecks";
import { LockKeyIcon } from "@phosphor-icons/react/dist/csr/LockKey";
import { LockSimpleIcon } from "@phosphor-icons/react/dist/csr/LockSimple";
import { LockSimpleOpenIcon } from "@phosphor-icons/react/dist/csr/LockSimpleOpen";
import { MagnifyingGlassIcon } from "@phosphor-icons/react/dist/csr/MagnifyingGlass";
import { MinusIcon } from "@phosphor-icons/react/dist/csr/Minus";
import { MoonIcon } from "@phosphor-icons/react/dist/csr/Moon";
import { NotebookIcon } from "@phosphor-icons/react/dist/csr/Notebook";
import { PaperclipIcon } from "@phosphor-icons/react/dist/csr/Paperclip";
import { PauseCircleIcon } from "@phosphor-icons/react/dist/csr/PauseCircle";
import { PencilSimpleIcon } from "@phosphor-icons/react/dist/csr/PencilSimple";
import { PencilSimpleLineIcon } from "@phosphor-icons/react/dist/csr/PencilSimpleLine";
import { PlusIcon } from "@phosphor-icons/react/dist/csr/Plus";
import { ProhibitIcon } from "@phosphor-icons/react/dist/csr/Prohibit";
import { QuestionIcon } from "@phosphor-icons/react/dist/csr/Question";
import { ReceiptIcon } from "@phosphor-icons/react/dist/csr/Receipt";
import { ScalesIcon } from "@phosphor-icons/react/dist/csr/Scales";
import { SealCheckIcon } from "@phosphor-icons/react/dist/csr/SealCheck";
import { ShieldCheckIcon } from "@phosphor-icons/react/dist/csr/ShieldCheck";
import { SidebarSimpleIcon } from "@phosphor-icons/react/dist/csr/SidebarSimple";
import { SignOutIcon } from "@phosphor-icons/react/dist/csr/SignOut";
import { SparkleIcon } from "@phosphor-icons/react/dist/csr/Sparkle";
import { SunIcon } from "@phosphor-icons/react/dist/csr/Sun";
import { TableIcon } from "@phosphor-icons/react/dist/csr/Table";
import { TrashIcon } from "@phosphor-icons/react/dist/csr/Trash";
import { TreeStructureIcon } from "@phosphor-icons/react/dist/csr/TreeStructure";
import { UploadSimpleIcon } from "@phosphor-icons/react/dist/csr/UploadSimple";
import { WarningCircleIcon } from "@phosphor-icons/react/dist/csr/WarningCircle";
import { XIcon } from "@phosphor-icons/react/dist/csr/X";
import { XCircleIcon } from "@phosphor-icons/react/dist/csr/XCircle";
import type { Icon } from "@phosphor-icons/react/dist/lib/types";

export { IconContext } from "@phosphor-icons/react/dist/lib/context";
export type { Icon, IconProps } from "@phosphor-icons/react/dist/lib/types";

/** DS-ICO-07, keyed by the Phosphor core name. */
export const ICONS = {
  ArrowSquareOut: ArrowSquareOutIcon,
  ArrowsClockwise: ArrowsClockwiseIcon,
  ArrowUUpLeft: ArrowUUpLeftIcon,
  Bell: BellIcon,
  Books: BooksIcon,
  Buildings: BuildingsIcon,
  CalendarBlank: CalendarBlankIcon,
  CalendarDots: CalendarDotsIcon,
  CaretDown: CaretDownIcon,
  CaretLeft: CaretLeftIcon,
  CaretRight: CaretRightIcon,
  CaretUp: CaretUpIcon,
  ChartBar: ChartBarIcon,
  ChatText: ChatTextIcon,
  CheckCircle: CheckCircleIcon,
  Circle: CircleIcon,
  CircleDashed: CircleDashedIcon,
  CircleHalf: CircleHalfIcon,
  ClockCounterClockwise: ClockCounterClockwiseIcon,
  Columns: ColumnsIcon,
  Command: CommandIcon,
  CopySimple: CopySimpleIcon,
  Database: DatabaseIcon,
  DotsThree: DotsThreeIcon,
  DownloadSimple: DownloadSimpleIcon,
  Equals: EqualsIcon,
  FileText: FileTextIcon,
  Function: FunctionIcon,
  Funnel: FunnelIcon,
  GearSix: GearSixIcon,
  HourglassMedium: HourglassMediumIcon,
  House: HouseIcon,
  Info: InfoIcon,
  Keyboard: KeyboardIcon,
  ListChecks: ListChecksIcon,
  LockKey: LockKeyIcon,
  LockSimple: LockSimpleIcon,
  LockSimpleOpen: LockSimpleOpenIcon,
  MagnifyingGlass: MagnifyingGlassIcon,
  Minus: MinusIcon,
  Moon: MoonIcon,
  Notebook: NotebookIcon,
  Paperclip: PaperclipIcon,
  PauseCircle: PauseCircleIcon,
  PencilSimple: PencilSimpleIcon,
  PencilSimpleLine: PencilSimpleLineIcon,
  Plus: PlusIcon,
  Prohibit: ProhibitIcon,
  Question: QuestionIcon,
  Receipt: ReceiptIcon,
  Scales: ScalesIcon,
  SealCheck: SealCheckIcon,
  ShieldCheck: ShieldCheckIcon,
  SidebarSimple: SidebarSimpleIcon,
  SignOut: SignOutIcon,
  Sparkle: SparkleIcon,
  Sun: SunIcon,
  Table: TableIcon,
  Trash: TrashIcon,
  TreeStructure: TreeStructureIcon,
  UploadSimple: UploadSimpleIcon,
  WarningCircle: WarningCircleIcon,
  X: XIcon,
  XCircle: XCircleIcon,
} as const satisfies Readonly<Record<string, Icon>>;

export type IconName = keyof typeof ICONS;

export const {
  ArrowSquareOut,
  ArrowsClockwise,
  ArrowUUpLeft,
  Bell,
  Books,
  Buildings,
  CalendarBlank,
  CalendarDots,
  CaretDown,
  CaretLeft,
  CaretRight,
  CaretUp,
  ChartBar,
  ChatText,
  CheckCircle,
  Circle,
  CircleDashed,
  CircleHalf,
  ClockCounterClockwise,
  Columns,
  Command,
  CopySimple,
  Database,
  DotsThree,
  DownloadSimple,
  Equals,
  FileText,
  Function,
  Funnel,
  GearSix,
  HourglassMedium,
  House,
  Info,
  Keyboard,
  ListChecks,
  LockKey,
  LockSimple,
  LockSimpleOpen,
  MagnifyingGlass,
  Minus,
  Moon,
  Notebook,
  Paperclip,
  PauseCircle,
  PencilSimple,
  PencilSimpleLine,
  Plus,
  Prohibit,
  Question,
  Receipt,
  Scales,
  SealCheck,
  ShieldCheck,
  SidebarSimple,
  SignOut,
  Sparkle,
  Sun,
  Table,
  Trash,
  TreeStructure,
  UploadSimple,
  WarningCircle,
  X,
  XCircle,
} = ICONS;

/** DS-ICO-08: icons that receive `mirrored` when `dir="rtl"`. */
export const MIRRORED_ICONS: ReadonlySet<IconName> = new Set<IconName>([
  "CaretRight",
  "CaretLeft",
  "ArrowSquareOut",
  "ArrowUUpLeft",
  "SidebarSimple",
  "TreeStructure",
]);

/** DS-ICO-04: the app root default; 12 px inside chips and sort indicators, 20 px in the rail. */
export const ICON_DEFAULTS = { size: 16, weight: "regular" } as const;
