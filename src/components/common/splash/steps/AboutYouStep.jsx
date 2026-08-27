import { useState } from "react";
import { VStack, HStack, Input, NativeSelect, Field } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { InfoIcon } from "../../icons";
import { SPECIALTIES } from "../../../../utils/constants";
import { validatePersonalStep } from "../../../../utils/splash/validators";

export const usePersonalStep = () => {
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");

  return {
    name,
    setName,
    specialty,
    setSpecialty,
    validate: () => validatePersonalStep(name, specialty),
    getData: () => ({ name, specialty }),
  };
};

export const AboutYouStep = ({
  name,
  setName,
  specialty,
  setSpecialty,
  letters,
}) => (
  <VStack key="about-you" className="anim-fade-slide-right" gap={4} w="100%">
    <Field.Root required>
      <HStack>
        <Field.Label fontSize="sm" color="textSecondary">نام شما</Field.Label>
        <Tooltip content="برای شخصی‌سازی تجربه شما و اسناد تولیدشده استفاده می‌شود" showArrow>
          <InfoIcon boxSize={3} color="textSecondary" />
        </Tooltip>
      </HStack>
      <Input
        placeholder="آدا لاولیس"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="input-style"
        size="sm"
      />
    </Field.Root>

    <Field.Root required>
      <HStack>
        <Field.Label fontSize="sm" color="textSecondary">تخصص شما</Field.Label>
        <Tooltip content="تخصص پزشکی شما به فلوکس کمک می‌کند راهنمایی مرتبط‌تری ارائه دهد" showArrow>
          <InfoIcon boxSize={3} color="textSecondary" />
        </Tooltip>
      </HStack>
      <NativeSelect.Root>
        <NativeSelect.Field
          placeholder="تخصص خود را انتخاب کنید"
          value={specialty}
          onChange={(e) => setSpecialty(e.target.value)}
          className="input-style"
          size="sm"
        >
          {SPECIALTIES.map((spec) => (
            <option key={spec} value={spec}>{spec}</option>
          ))}
        </NativeSelect.Field>
        <NativeSelect.Indicator />
      </NativeSelect.Root>
    </Field.Root>

    {/* Letter template — optional */}
    {letters && letters.availableLetterTemplates.length > 0 && (
      <Field.Root>
        <HStack>
          <Field.Label fontSize="sm" color="textSecondary">قالب پیش‌فرض نامه</Field.Label>
          <Tooltip content="هنگام تولید نامه استفاده می‌شود. اختیاری است و بعداً می‌توانید آن را تنظیم کنید." showArrow>
            <InfoIcon boxSize={3} color="textSecondary" />
          </Tooltip>
        </HStack>
        <NativeSelect.Root>
          <NativeSelect.Field
            placeholder="قالب نامه را انتخاب کنید"
            value={letters.selectedLetterTemplate}
            onChange={(e) => letters.setSelectedLetterTemplate(e.target.value)}
            className="input-style"
            size="sm"
          >
            {letters.availableLetterTemplates.map((t) => (
              <option key={t.id} value={t.id.toString()}>{t.name}</option>
            ))}
          </NativeSelect.Field>
          <NativeSelect.Indicator />
        </NativeSelect.Root>
      </Field.Root>
    )}
  </VStack>
);
