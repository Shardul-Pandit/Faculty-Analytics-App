import { clsx } from "clsx";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

interface AlertProps {
  type?: "error" | "success" | "info";
  message: string;
  className?: string;
}

const config = {
  error:   { icon: AlertCircle,    bg: "bg-red-50",   border: "border-red-200",   text: "text-red-800",   iconColor: "text-red-500"   },
  success: { icon: CheckCircle2,   bg: "bg-green-50", border: "border-green-200", text: "text-green-800", iconColor: "text-green-500" },
  info:    { icon: Info,           bg: "bg-blue-50",  border: "border-blue-200",  text: "text-blue-800",  iconColor: "text-blue-500"  },
};

export function Alert({ type = "info", message, className }: AlertProps) {
  const { icon: Icon, bg, border, text, iconColor } = config[type];
  return (
    <div
      className={clsx(
        "flex items-start gap-3 rounded-lg border px-4 py-3 text-sm",
        bg, border, text, className
      )}
    >
      <Icon className={clsx("mt-0.5 h-4 w-4 shrink-0", iconColor)} />
      <span>{message}</span>
    </div>
  );
}
