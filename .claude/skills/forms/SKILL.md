---
name: forms
description: Building forms in this project — react-hook-form + zod schemas generated from the FastAPI/Pydantic models, shadcn Field components, submitting through TanStack Query mutations and mapping FastAPI 422 errors back onto fields. Use this skill for any form, input validation, submit button, login/register form, create/edit dialog, or when the user asks to "add a form", "validate", "форма", "валидация", "поля", even if they don't mention react-hook-form or zod.
---

# Forms: react-hook-form 7.88 + zod 4.6 + shadcn Field

Validation rules come from the backend: `npm run gen` turns every Pydantic model into a zod schema in `src/client/zod.gen.ts` (`OrderCreate` → `zOrderCreate`). The form validates exactly what FastAPI will validate, and when the backend model changes, the form's types break at compile time instead of in production.

## Template

```tsx
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import { createOrderMutation, listServicesQueryKey } from '@/client/@tanstack/react-query.gen'
import { zOrderCreate } from '@/client/zod.gen'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { getFieldErrors } from '@/lib/api-error'

// Start from the generated schema; add UI-only rules with .extend()
const schema = zOrderCreate.extend({
  address: z.string().trim().min(5, 'Укажите адрес полностью'),
})
type FormValues = z.infer<typeof schema>

export function OrderForm({ onDone }: { onDone?: () => void }) {
  const qc = useQueryClient()
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { service_id: 1, address: '' }, // always provide defaults
  })

  const order = useMutation({
    ...createOrderMutation(),
    meta: { silent: true }, // errors are shown on fields instead of the global toast
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: listServicesQueryKey() })
      form.reset()
      onDone?.()
    },
    onError: (error) => {
      // FastAPI 422 -> field errors
      for (const [field, message] of Object.entries(getFieldErrors(error))) {
        form.setError(field as keyof FormValues, { message })
      }
    },
  })

  return (
    <form onSubmit={form.handleSubmit((body) => order.mutate({ body }))}>
      <FieldGroup>
        {/* Native inputs: register() */}
        <Field data-invalid={!!form.formState.errors.address}>
          <FieldLabel htmlFor="address">Адрес</FieldLabel>
          <Input id="address" aria-invalid={!!form.formState.errors.address} {...form.register('address')} />
          <FieldError errors={[form.formState.errors.address]} />
        </Field>

        {/* Non-native controls (Select, Checkbox, Switch...): Controller */}
        <Controller
          control={form.control}
          name="service_id"
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel>Услуга</FieldLabel>
              <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">Вывоз мусора</SelectItem>
                </SelectContent>
              </Select>
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />

        <Button type="submit" disabled={order.isPending}>
          {order.isPending ? 'Отправляем…' : 'Отправить'}
        </Button>
      </FieldGroup>
    </form>
  )
}
```

This exact pattern compiles against the project's shadcn (Base UI, nova) components.

## Rules

- Base the schema on the generated `zXxx`; never retype the model by hand. Use `.extend()` / `.pick()` / `.omit()` for form-specific differences.
- Field names stay snake_case like the backend (`service_id`), so `getFieldErrors` maps 422 errors onto the right fields.
- Use `register` for `Input`/`Textarea`; use `Controller` for Base UI controls (`Select`, `Checkbox`, `Switch`, `RadioGroup`, `Slider`) — they don't expose a native input to register.
- Numbers from inputs are strings: use `z.coerce.number()` in the extended schema or `register('x', { valueAsNumber: true })`.
- Put `aria-invalid` on the control and `data-invalid` on `Field` — the shadcn styles key off them.
- Disable submit with `order.isPending`, not a separate `useState`.
- Login forms: FastAPI's OAuth2 form uses `username`/`password` fields; use `zBodyLogin` (or whatever `npm run gen` produced for the login body) and `loginMutation()`.
- Add missing shadcn pieces with `npx shadcn@4.21.0 add textarea checkbox switch` — never hand-write them.
