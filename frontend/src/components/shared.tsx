import {
  useEffect,
  useId,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  ImageIcon,
  Package,
  Pause,
  Play,
  Upload,
  X,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { usePage } from "@/lib/page";
import { cn } from "@/lib/utils";
export function LinkButton({
  href,
  children,
  variant = "default",
  ...props
}: { href: string; children: ReactNode } & ComponentProps<typeof Button>) {
  return (
    <Button asChild variant={variant} {...props}>
      <a href={href}>{children}</a>
    </Button>
  );
}
export function Heading({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  useEffect(() => {
    document.title = `${title} · R19 Finder`;
  }, [title]);
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}
export function Back({
  href = "/",
  children = "Back to requests",
}: {
  href?: string;
  children?: ReactNode;
}) {
  return (
    <a className="back-link" href={href}>
      <ChevronLeft size={15} />
      {children}
    </a>
  );
}
export function Section({
  title,
  description,
  children,
  className,
  action,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <section className={cn("surface", className)}>
      {title && (
        <div className="section-heading">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Empty({
  title,
  description,
  action,
  icon: Icon = Package,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: typeof Package;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon size={28} strokeWidth={1.5} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Notice({
  children,
  error = false,
  onDismiss,
}: {
  children: ReactNode;
  error?: boolean;
  onDismiss?: () => void;
}) {
  return (
    <div
      className={cn("notice", error && "notice-error")}
      role={error ? "alert" : "status"}
    >
      {error ? <AlertCircle size={18} /> : <Check size={18} />}
      <div>{children}</div>
      {onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Dismiss notification"
          onClick={onDismiss}
        >
          <X size={16} />
        </Button>
      )}
    </div>
  );
}
const labels: Record<string, string> = {
  completed: "Results ready",
  running: "Searching",
  queued: "In queue",
  failed: "Needs attention",
  new: "Ready to search",
  ok: "Connected",
  error: "Connection issue",
  untested: "Not checked",
};
export function Status({
  status = "new",
  label,
}: {
  status?: string;
  label?: string;
}) {
  return (
    <Badge variant="outline" className={cn("status", `status-${status}`)}>
      <span className="status-dot" />
      {label || labels[status] || status}
    </Badge>
  );
}
export function CSRF() {
  return <input type="hidden" name="csrf" value={usePage().csrf} />;
}
export function PostForm({
  children,
  className,
  ...props
}: ComponentProps<"form">) {
  const [busy, setBusy] = useState(false);
  return (
    <form
      method="post"
      className={className}
      {...props}
      onSubmit={(e) => {
        if (busy) {
          e.preventDefault();
          return;
        }
        props.onSubmit?.(e);
        if (!e.defaultPrevented) setBusy(true);
      }}
      aria-busy={busy}
    >
      <CSRF />
      {children}
      {busy && (
        <p role="status" className="help mt-3">
          Saving. Please wait…
        </p>
      )}
    </form>
  );
}
export function Field({
  label,
  help,
  name,
  textarea,
  ...props
}: {
  label: string;
  help?: string;
  name: string;
  textarea?: boolean;
} & ComponentProps<"input"> & { rows?: number }) {
  const id = useId();
  return (
    <div className="field">
      <Label htmlFor={id}>
        {label}
        {props.required && <span className="required">*</span>}
      </Label>
      {textarea ? (
        <Textarea
          id={id}
          name={name}
          aria-describedby={help ? id + "-help" : undefined}
          {...(props as ComponentProps<"textarea">)}
        />
      ) : (
        <Input
          id={id}
          name={name}
          aria-describedby={help ? id + "-help" : undefined}
          {...props}
        />
      )}{" "}
      {help && (
        <p id={id + "-help"} className="help">
          {help}
        </p>
      )}
    </div>
  );
}
export function Choice({
  label,
  name,
  options,
  value,
  defaultValue = "",
  onValueChange,
  help,
  disabled = false,
}: {
  label: string;
  name?: string;
  options: { value: string; label: string }[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  help?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="field">
      <Label htmlFor={id}>{label}</Label>
      <Select
        name={name}
        value={value === "" ? "__empty" : value}
        defaultValue={defaultValue || "__empty"}
        onValueChange={(v) => onValueChange?.(v === "__empty" ? "" : v)}
        disabled={disabled}
      >
        <SelectTrigger
          id={id}
          className="w-full"
          aria-describedby={help ? id + "-help" : undefined}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value || "__empty"}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {help && (
        <p className="help" id={id + "-help"}>
          {help}
        </p>
      )}
    </div>
  );
}
// Native form actions need an actual empty value, whereas Radix reserves it.
export function FormChoice(props: ComponentProps<typeof Choice>) {
  const [v, setV] = useState(props.defaultValue || "");
  return (
    <>
      <Choice
        {...props}
        name={undefined}
        value={props.value ?? v}
        onValueChange={(value) => {
          setV(value);
          props.onValueChange?.(value);
        }}
      />
      <input type="hidden" name={props.name} value={props.value ?? v} />
    </>
  );
}
export function CheckField({
  label,
  name,
  value = "1",
  defaultChecked,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: ReactNode;
  name?: string;
  value?: string;
  defaultChecked?: boolean;
  checked?: boolean;
  onCheckedChange?: (v: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="check-field">
      <Checkbox
        id={id}
        name={name}
        value={value}
        defaultChecked={defaultChecked}
        checked={checked}
        onCheckedChange={(v) => onCheckedChange?.(v === true)}
        disabled={disabled}
      />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}
export function Photo({
  src,
  alt,
  className,
}: {
  src?: string;
  alt: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={cn("photo-frame", className)}>
      {src && !failed ? (
        <img
          src={src}
          alt={alt}
          onError={() => setFailed(true)}
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="photo-placeholder">
          <ImageIcon size={26} strokeWidth={1.25} />
          <span>No photo available</span>
        </div>
      )}
    </div>
  );
}
export function Gallery({ photos, name }: { photos: string[]; name: string }) {
  const [index, setIndex] = useState(0);
  const reduced = useReducedMotion();
  const [play, setPlay] = useState(false);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    setPlay(!reduced);
  }, [reduced]);
  useEffect(() => {
    if (!play || paused || photos.length < 2) return;
    const timer = setInterval(() => {
      if (!document.hidden) setIndex((i) => (i + 1) % photos.length);
    }, 5000);
    return () => clearInterval(timer);
  }, [play, paused, photos.length]);
  function select(i: number) {
    setIndex((i + photos.length) % photos.length);
    setPlay(false);
  }
  return (
    <div
      className="gallery"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setPaused(false);
      }}
    >
      <motion.div
        key={photos[index] || "empty"}
        initial={{ opacity: reduced ? 1 : 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: reduced ? 0 : 0.18 }}
      >
        <Photo src={photos[index]} alt={`${name}, photo ${index + 1}`} />
      </motion.div>
      {photos.length > 1 && (
        <div className="gallery-controls">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => select(index - 1)}
            aria-label="Previous photo"
          >
            <ChevronLeft />
          </Button>
          <span>
            {index + 1} / {photos.length}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => select(index + 1)}
            aria-label="Next photo"
          >
            <ChevronRight />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => setPlay(!play)}
            aria-label={play ? "Pause slideshow" : "Play slideshow"}
          >
            {play ? <Pause /> : <Play />}
          </Button>
        </div>
      )}
    </div>
  );
}
export function UploadPhotos({
  car = false,
  resetKey = 0,
}: {
  car?: boolean;
  resetKey?: number;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setUrls] = useState<string[]>([]);
  const id = useId();
  useEffect(() => {
    const next = files.map((f) => URL.createObjectURL(f));
    setUrls(next);
    return () => next.forEach(URL.revokeObjectURL);
  }, [files]);
  useEffect(() => setFiles([]), [resetKey]);
  return (
    <div className="upload-block">
      <Label htmlFor={id}>
        <Upload size={22} />
        <span>Choose reference photos</span>
      </Label>
      <Input
        key={resetKey}
        id={id}
        name="photos"
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        onChange={(e) => setFiles(Array.from(e.target.files || []))}
      />
      <p className="help">
        {car
          ? "JPG, PNG or WebP · 32 MB per upload."
          : "JPG, PNG or WebP · 6 photos total · 5 MB each."}
      </p>
      {files.length > 0 && (
        <>
          <p role="status" className="help">
            {files.length} photo{files.length === 1 ? "" : "s"} selected
          </p>
          <div className="photo-grid">
            {urls.map((url, i) => (
              <Photo
                key={url}
                src={url}
                alt={files[i]?.name || "Selected photo"}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
export function ArrowLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a href={href} className="text-link">
      {children}
      <ArrowRight size={15} />
    </a>
  );
}
